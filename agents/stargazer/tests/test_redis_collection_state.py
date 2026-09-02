import asyncio
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio
from core.collection.application import CollectionApplication, CollectionApplicationSettings
from core.collection.contracts import CollectOutcome, CollectOutcomeStatus, PreflightResult, PreflightStatus
from core.collection.credential_policy import CredentialPolicy
from core.collection.host_remote import callback as callback_state
from core.collection.redis_state import RedisCredentialStateStore, RedisRunStateStore
from core.collection.runtime import CollectionRequest, LeaseAcquireStatus, RunStatus
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError


def _stop_redis(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture
def redis_socket(tmp_path):
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("redis-server is not installed")
    socket_path = Path("/tmp") / f"stargazer-runtime-{secrets.token_hex(6)}.sock"
    process = subprocess.Popen(
        [
            executable,
            "--save",
            "",
            "--appendonly",
            "no",
            "--port",
            "0",
            "--unixsocket",
            str(socket_path),
            "--unixsocketperm",
            "700",
            "--dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    probe = Redis(unix_socket_path=str(socket_path), db=14)
    try:
        for _attempt in range(100):
            try:
                if probe.ping():
                    break
            except (RedisConnectionError, OSError):
                time.sleep(0.01)
        else:
            pytest.fail("temporary redis-server did not start")
        yield socket_path
    finally:
        probe.close()
        _stop_redis(process)
        socket_path.unlink(missing_ok=True)


@pytest_asyncio.fixture
async def redis_client(redis_socket):
    client = AsyncRedis(
        unix_socket_path=str(redis_socket),
        db=14,
        decode_responses=True,
    )
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.asyncio
async def test_two_pods_atomically_share_one_run_lease(redis_client):
    first_store = RedisRunStateStore(redis_client, key_prefix="test:runtime")
    second_store = RedisRunStateStore(redis_client, key_prefix="test:runtime")

    first = await first_store.acquire(
        task_id="collect-001",
        request_digest="digest-a",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    duplicate = await second_store.acquire(
        task_id="collect-001",
        request_digest="digest-a",
        owner_id="pod-b",
        ttl_seconds=60,
    )

    assert first.status == LeaseAcquireStatus.ACQUIRED
    assert duplicate.status == LeaseAcquireStatus.DUPLICATE_ACTIVE
    assert first.lease is not None
    assert duplicate.lease is not None
    assert duplicate.lease.owner_id == "pod-a"
    assert duplicate.lease.fence == first.lease.fence == 1
    assert duplicate.lease.attempt_id == first.lease.attempt_id
    assert first.lease.attempt_id


@pytest.mark.asyncio
async def test_run_acquire_persists_latest_generation_tombstone(redis_client):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:generation")

    acquisition = await run_store.acquire(
        task_id="collect-generation",
        request_digest="digest-a",
        owner_id="pod-a",
        ttl_seconds=60,
    )

    assert acquisition.lease is not None
    latest_generation = await redis_client.hgetall(run_store._fence_key("collect-generation"))
    assert latest_generation == {
        "owner_id": acquisition.lease.owner_id,
        "fence": str(acquisition.lease.fence),
        "attempt_id": acquisition.lease.attempt_id,
    }
    assert await redis_client.pttl(run_store._fence_key("collect-generation")) > 0


@pytest.mark.asyncio
async def test_callback_record_rechecks_latest_finished_generation_atomically(
    redis_client,
    monkeypatch,
):
    monkeypatch.setenv(
        "HOST_REMOTE_CALLBACK_TOKEN_SECRET",
        "issue-4280-test-token-secret-with-32-bytes",
    )
    monkeypatch.setattr(callback_state, "_host_remote_callback_pool", redis_client)
    run_store = RedisRunStateStore(redis_client)
    first = await run_store.acquire(
        task_id="callback-generation",
        request_digest="digest-a",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    assert first.lease is not None
    callback_identity, trusted_identity = callback_state.issue_host_remote_callback_identity(
        fence=first.lease.fence,
        target="10.0.0.1",
        collection_task_id=first.lease.task_id,
        plugin_ref="host.monitor",
        owner_id=first.lease.owner_id,
        attempt=first.lease.attempt_id,
        caller="executor-a",
    )
    callback_task_id = "remote-v2-generation-race"
    await callback_state.store_host_remote_callback_context(
        callback_task_id,
        {"host": "10.0.0.1"},
        trusted_identity,
        ttl_seconds=60,
    )
    assert await run_store.finish(first.lease, RunStatus.COMPLETED)
    second = await run_store.acquire(
        task_id="callback-generation",
        request_digest="digest-b",
        owner_id="pod-b",
        ttl_seconds=60,
    )
    assert second.lease is not None
    assert await run_store.finish(second.lease, RunStatus.FAILED)

    with pytest.raises(RuntimeError, match="latest generation is stale"):
        await callback_state.record_host_remote_callback_payload(
            callback_task_id,
            {
                "task_id": callback_task_id,
                "callback_context": callback_identity,
                "result": {"cpu": 1},
            },
        )

    stored = await callback_state.load_host_remote_callback_context(callback_task_id)
    assert stored["raw_callback"] is None


@pytest.mark.asyncio
async def test_callback_record_removes_consumed_token_from_redis(
    redis_client,
    monkeypatch,
):
    monkeypatch.setenv(
        "HOST_REMOTE_CALLBACK_TOKEN_SECRET",
        "issue-4280-test-token-secret-with-32-bytes",
    )
    monkeypatch.setattr(callback_state, "_host_remote_callback_pool", redis_client)
    run_store = RedisRunStateStore(redis_client)
    acquisition = await run_store.acquire(
        task_id="callback-token-redaction",
        request_digest="digest",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    assert acquisition.lease is not None
    callback_identity, trusted_identity = callback_state.issue_host_remote_callback_identity(
        fence=acquisition.lease.fence,
        target="10.0.0.1",
        collection_task_id=acquisition.lease.task_id,
        plugin_ref="host.monitor",
        owner_id=acquisition.lease.owner_id,
        attempt=acquisition.lease.attempt_id,
        caller="executor-a",
    )
    callback_task_id = "remote-v2-token-redaction"
    await callback_state.store_host_remote_callback_context(
        callback_task_id,
        {"host": "10.0.0.1"},
        trusted_identity,
        ttl_seconds=60,
    )
    assert await run_store.finish(acquisition.lease, RunStatus.COMPLETED)

    stored = await callback_state.record_host_remote_callback_payload(
        callback_task_id,
        {
            "task_id": callback_task_id,
            "callback_context": callback_identity,
            "result": {"cpu": 1},
        },
    )

    assert "token" not in stored["ctx"]
    assert "token" not in stored["raw_callback"]["callback_context"]
    assert stored["ctx"]["token_hash"] == trusted_identity["token_hash"]


@pytest.mark.asyncio
async def test_heartbeat_extends_only_the_current_fenced_lease(redis_client):
    first_store = RedisRunStateStore(redis_client, key_prefix="test:heartbeat")
    second_store = RedisRunStateStore(redis_client, key_prefix="test:heartbeat")
    first = await first_store.acquire(
        task_id="collect-heartbeat",
        request_digest="digest-a",
        owner_id="pod-a",
        ttl_seconds=0.05,
    )
    assert first.lease is not None

    renewed = await first_store.heartbeat(first.lease, ttl_seconds=0.2)
    await asyncio.sleep(0.06)
    duplicate = await second_store.acquire(
        task_id="collect-heartbeat",
        request_digest="digest-a",
        owner_id="pod-b",
        ttl_seconds=0.05,
    )

    assert renewed is True
    assert duplicate.status == LeaseAcquireStatus.DUPLICATE_ACTIVE
    assert duplicate.lease is not None
    assert duplicate.lease.fence == 1


@pytest.mark.asyncio
async def test_credential_affinity_and_cooldown_are_shared_without_storing_secrets(
    redis_client,
):
    first_policy = CredentialPolicy(store=RedisCredentialStateStore(redis_client, key_prefix="test:credential"))
    second_policy = CredentialPolicy(store=RedisCredentialStateStore(redis_client, key_prefix="test:credential"))
    request = CollectionRequest(
        task_id="collect-credential",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {
                "credential_id": "credential-1",
                "username": "root",
                "password": "do-not-store-one",
            },
            {
                "credential_id": "credential-2",
                "username": "readonly",
                "password": "do-not-store-two",
            },
        ),
        params={"scope_id": "tenant-a", "credential_set_version": "v1"},
    )

    await first_policy.record_auth_failure(
        request,
        "10.10.24.1",
        request.credentials[0],
        error_code="unauthorized",
    )
    await first_policy.record_success(
        request,
        "10.10.24.1",
        request.credentials[1],
    )
    eligible = await second_policy.eligible_credentials(request, "10.10.24.1")

    assert [item["credential_id"] for item in eligible] == [
        "credential-2",
    ]
    keys = await redis_client.keys("test:credential:*")
    stored_values = [str(await redis_client.dump(key) or "") for key in keys]
    stored = " ".join(stored_values)
    assert "do-not-store-one" not in stored
    assert "do-not-store-two" not in stored


@pytest.mark.asyncio
async def test_credential_version_change_invalidates_only_edited_credential_state(redis_client):
    store = RedisCredentialStateStore(redis_client, key_prefix="test:credential-version")
    policy = CredentialPolicy(store=store, jitter=lambda _start, _end: 0)
    v1 = {"credential_id": "credential-1", "credential_version": 1}
    v2 = {"credential_id": "credential-1", "credential_version": 2}
    request_v1 = CollectionRequest(
        task_id="collect-version-v1",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(v1,),
        params={"scope_id": "task-131", "credential_set_version": "epoch-1"},
    )
    request_v2 = CollectionRequest(
        task_id="collect-version-v2",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(v2,),
        params={"scope_id": "task-131", "credential_set_version": "epoch-1"},
    )

    await policy.record_auth_failure(
        request_v1,
        "10.10.24.1",
        v1,
        error_code="unauthorized",
    )

    assert await policy.eligible_credentials(request_v1, "10.10.24.1") == ()
    assert await policy.eligible_credentials(request_v2, "10.10.24.1") == (v2,)


@pytest.mark.asyncio
async def test_expired_lease_can_be_reacquired_by_next_owner(redis_client):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:checkpoint")
    first = await run_store.acquire(
        task_id="collect-takeover",
        request_digest="digest-a",
        owner_id="pod-a",
        ttl_seconds=0.02,
    )
    assert first.lease is not None
    await asyncio.sleep(0.03)
    second = await run_store.acquire(
        task_id="collect-takeover",
        request_digest="digest-a",
        owner_id="pod-b",
        ttl_seconds=60,
    )
    assert second.lease is not None
    assert second.status == LeaseAcquireStatus.ACQUIRED
    assert second.lease.fence == 1
    assert first.lease.owner_id != second.lease.owner_id


@pytest.mark.asyncio
async def test_finish_releases_lease_for_next_cycle(redis_client):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:finish")
    first = await run_store.acquire(
        task_id="cycle-1",
        request_digest="digest",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    assert first.lease is not None
    assert await run_store.finish(first.lease, status=RunStatus.COMPLETED, summary={"total": 1})
    second = await run_store.acquire(
        task_id="cycle-1",
        request_digest="digest",
        owner_id="pod-b",
        ttl_seconds=60,
    )
    assert second.status == LeaseAcquireStatus.ACQUIRED
    assert second.lease is not None
    assert second.lease.owner_id == "pod-b"
    assert second.lease.fence == 1
    assert second.lease.attempt_id != first.lease.attempt_id


@pytest.mark.asyncio
async def test_previous_cycle_cannot_finish_or_heartbeat_new_same_owner_lease(
    redis_client,
):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:attempt-fence")
    first = await run_store.acquire(
        task_id="cycle-same-owner",
        request_digest="digest",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    assert first.lease is not None
    assert await run_store.finish(first.lease, status=RunStatus.COMPLETED)
    second = await run_store.acquire(
        task_id="cycle-same-owner",
        request_digest="digest",
        owner_id="pod-a",
        ttl_seconds=60,
    )
    assert second.lease is not None
    assert second.lease.attempt_id != first.lease.attempt_id

    assert not await run_store.heartbeat(first.lease, ttl_seconds=60)
    assert not await run_store.finish(first.lease, status=RunStatus.COMPLETED)
    duplicate = await run_store.acquire(
        task_id="cycle-same-owner",
        request_digest="digest",
        owner_id="pod-b",
        ttl_seconds=60,
    )
    assert duplicate.status == LeaseAcquireStatus.DUPLICATE_ACTIVE
    assert duplicate.lease is not None
    assert duplicate.lease.attempt_id == second.lease.attempt_id


@pytest.mark.asyncio
async def test_application_runs_multi_target_request_and_allows_next_cycle(
    redis_client,
):
    published = []
    scheduled = []

    class Preflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            return PreflightResult(status=PreflightStatus.REACHABLE)

    class Plugin:
        async def collect(self, target, credential, context):
            return CollectOutcome(
                status=CollectOutcomeStatus.SUCCESS,
                value={"target": target},
            )

    class Factory:
        def resolve(self, request):
            return Plugin()

    class Publisher:
        async def publish(self, request, result, lease):
            published.append((request.task_id, result.target, lease.fence))

    def schedule(coroutine, *, name):
        task = asyncio.create_task(coroutine, name=name)
        scheduled.append(task)
        return task

    application = CollectionApplication(
        redis_client=redis_client,
        schedule=schedule,
        owner_id="pod-integration",
        settings=CollectionApplicationSettings(
            max_active_runs=2,
            max_active_targets=2,
            network_topology_max_active_targets=1,
            target_task_window=2,
            connect_timeout_seconds=1,
            plugin_timeout_seconds=1,
            lease_ttl_seconds=10,
            lease_heartbeat_seconds=1,
        ),
        plugin_factory=Factory(),
        preflight=Preflight(),
        publisher=Publisher(),
    )
    request = CollectionRequest(
        task_id="application-integration",
        plugin_ref="test.config",
        targets=("10.10.24.1", "10.10.24.2"),
        credentials=({"credential_id": "credential-1"},),
    )

    accepted = await application.submit(request)
    await scheduled[0]
    next_cycle = await application.submit(request)

    assert accepted.status.value == "accepted"
    assert next_cycle.status.value == "accepted"
    assert len(scheduled) == 2
    assert published == [
        (request.task_id, "10.10.24.1", 1),
        (request.task_id, "10.10.24.2", 1),
    ]
    await scheduled[1]


@pytest.mark.asyncio
async def test_load_target_state_uses_single_mget(redis_client, monkeypatch):
    store = RedisCredentialStateStore(redis_client, key_prefix="test:mget")
    request = CollectionRequest(
        task_id="collect-mget",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=(
            {"credential_id": "credential-1"},
            {"credential_id": "credential-2"},
        ),
        params={"scope_id": "tenant-a", "credential_set_version": "v1"},
    )
    policy = CredentialPolicy(store=store)
    await policy.record_success(request, "10.10.24.1", request.credentials[1])
    await policy.record_auth_failure(
        request,
        "10.10.24.1",
        request.credentials[0],
        error_code="unauthorized",
    )

    calls = {"mget": 0, "get": 0}
    original_mget = redis_client.mget
    original_get = redis_client.get

    async def counting_mget(*args, **kwargs):
        calls["mget"] += 1
        return await original_mget(*args, **kwargs)

    async def counting_get(*args, **kwargs):
        calls["get"] += 1
        return await original_get(*args, **kwargs)

    monkeypatch.setattr(redis_client, "mget", counting_mget)
    monkeypatch.setattr(redis_client, "get", counting_get)

    scope = policy._scope(request, "10.10.24.1")
    success_id, failures = await store.load_target_state(scope, ("credential-1", "credential-2"))

    assert success_id == "credential-2"
    assert failures["credential-1"] is not None
    assert failures["credential-2"] is None
    assert calls["mget"] == 1
    assert calls["get"] == 0
