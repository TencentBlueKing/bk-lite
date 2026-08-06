import asyncio
import secrets
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from core.collection_runtime import LeaseAcquireStatus, RunLease
from core.collection_runtime import CollectionRequest
from core.collection_application import (
    CollectionApplication,
    CollectionApplicationSettings,
)
from core.credential_policy import CredentialPolicy
from core.redis_collection_state import (
    RedisCredentialStateStore,
    RedisRunStateStore,
    RedisTargetCheckpointStore,
)
from core.target_collection_executor import TargetCollectionResult
from core.target_collection_executor import (
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
)


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
    first_policy = CredentialPolicy(
        store=RedisCredentialStateStore(redis_client, key_prefix="test:credential")
    )
    second_policy = CredentialPolicy(
        store=RedisCredentialStateStore(redis_client, key_prefix="test:credential")
    )
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
    eligible = await second_policy.eligible_credentials(
        request, "10.10.24.1"
    )

    assert [item["credential_id"] for item in eligible] == [
        "credential-2",
        "credential-1",
    ]
    keys = await redis_client.keys("test:credential:*")
    stored_values = [str(await redis_client.get(key) or "") for key in keys]
    stored = " ".join(stored_values)
    assert "do-not-store-one" not in stored
    assert "do-not-store-two" not in stored


@pytest.mark.asyncio
async def test_stale_fence_cannot_write_target_checkpoint(redis_client):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:checkpoint")
    checkpoint_store = RedisTargetCheckpointStore(
        redis_client, key_prefix="test:checkpoint"
    )
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
    result = TargetCollectionResult(
        target="10.10.24.1",
        status="success",
        attempts=1,
        credential_id="credential-2",
        value={"hostname": "db-01"},
    )

    stale_saved = await checkpoint_store.mark_completed(
        plugin_ref="mysql.config", result=result, lease=first.lease
    )
    current_saved = await checkpoint_store.mark_completed(
        plugin_ref="mysql.config", result=result, lease=second.lease
    )

    assert second.lease.fence > first.lease.fence
    assert stale_saved is False
    assert current_saved is True
    assert await checkpoint_store.is_completed(
        task_id="collect-takeover",
        plugin_ref="mysql.config",
        target="10.10.24.1",
    )
    assert not await checkpoint_store.is_current(first.lease)
    assert await checkpoint_store.is_current(second.lease)


@pytest.mark.asyncio
async def test_pending_result_survives_publish_failure_and_is_fenced(redis_client):
    run_store = RedisRunStateStore(redis_client, key_prefix="test:pending")
    checkpoints = RedisTargetCheckpointStore(redis_client, key_prefix="test:pending")
    acquired = await run_store.acquire(
        task_id="pending-1", request_digest="digest", owner_id="pod-a",
        ttl_seconds=60,
    )
    result = TargetCollectionResult(
        target="10.10.24.1", status="success", attempts=1, value={"ok": True}
    )
    assert await checkpoints.mark_publish_pending(
        plugin_ref="mysql.config", result=result, lease=acquired.lease
    )
    assert not await checkpoints.is_completed(
        task_id="pending-1", plugin_ref="mysql.config", target=result.target
    )
    assert await checkpoints.load_pending(
        task_id="pending-1", plugin_ref="mysql.config", target=result.target
    ) == result
    assert await checkpoints.begin_publish(acquired.lease, guard_seconds=30)


@pytest.mark.asyncio
async def test_application_runs_one_multi_target_request_and_reuses_summary(
    redis_client,
):
    published = []
    scheduled = []

    class Preflight:
        async def check(self, target, request, *, timeout_seconds):
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
    completed = await application.submit(request)

    assert accepted.status.value == "accepted"
    assert len(scheduled) == 1
    assert published == [
        (request.task_id, "10.10.24.1", 1),
        (request.task_id, "10.10.24.2", 1),
    ]
    assert completed.status.value == "completed"
    assert completed.summary == {
        "deferred": 0,
        "failed": 0,
        "skipped": 0,
        "succeeded": 2,
        "total": 2,
        "unreachable": 0,
    }
