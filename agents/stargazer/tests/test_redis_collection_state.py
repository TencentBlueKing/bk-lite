import asyncio
import json
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from core.collection.application import CollectionApplication, CollectionApplicationSettings
from core.collection.contracts import CollectOutcome, CollectOutcomeStatus, PreflightResult, PreflightStatus
from core.collection.credential_policy import CredentialPolicy
from core.collection.redis_state import RedisCredentialStateStore, RedisRunStateStore
from core.collection.runtime import CollectionRequest, LeaseAcquireStatus, RunStatus
from core.infra.credential_state_cache import CredentialStateCache
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError


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
async def test_result_event_redis_write_is_retryable_and_cursor_keeps_same_millisecond(redis_client, monkeypatch):
    async def get_client():
        return redis_client

    monkeypatch.setattr(
        CredentialStateCache,
        "_get_or_create_pool",
        classmethod(lambda _cls: get_client()),
    )
    stream_key = CredentialStateCache._event_stream_key()
    failed_event_id = "event-failed-once"
    await redis_client.set(stream_key, "wrong-type")

    with pytest.raises(ResponseError):
        await CredentialStateCache.append_result_event(
            {
                "event_id": failed_event_id,
                "finished_at": "2026-08-14T00:00:00.123+00:00",
            }
        )

    assert not await redis_client.exists(CredentialStateCache._event_dedupe_key(failed_event_id))
    await redis_client.delete(stream_key)
    for event_id in ("event-001", "event-002", "event-003"):
        await CredentialStateCache.append_result_event(
            {
                "event_id": event_id,
                "finished_at": "2026-08-14T00:00:00.123+00:00",
            }
        )
    await CredentialStateCache.append_result_event(
        {
            "event_id": failed_event_id,
            "finished_at": "2026-08-14T00:00:00.123+00:00",
        }
    )

    first_page = await CredentialStateCache.list_result_events(limit=2)
    first_cursor = CredentialStateCache.event_cursor(first_page[-1])
    second_page = await CredentialStateCache.list_result_events(since=first_cursor, limit=2)
    legacy_cursor_page = await CredentialStateCache.list_result_events(since="2026-08-14T00:00:00.123+00:00", limit=10)

    assert [event["event_id"] for event in first_page] == [
        "event-001",
        "event-002",
    ]
    assert [event["event_id"] for event in second_page] == [
        "event-003",
        failed_event_id,
    ]
    assert len(legacy_cursor_page) == 4
    assert all(CredentialStateCache._STREAM_CURSOR_FIELD in event for event in first_page + second_page)
    await CredentialStateCache.set_push_cursor(first_cursor)
    assert await CredentialStateCache.get_push_cursor() == first_cursor
    legacy_cursor = await redis_client.get(CredentialStateCache._push_cursor_key())
    if isinstance(legacy_cursor, bytes):
        legacy_cursor = legacy_cursor.decode()
    assert legacy_cursor == first_page[-1]["finished_at"]
    assert CredentialStateCache._event_score(legacy_cursor) > 0
    legacy_raw_page = await redis_client.zrangebyscore(
        stream_key,
        min=f"({CredentialStateCache._event_score(legacy_cursor)}",
        max="+inf",
        start=0,
        num=2,
    )
    assert [CredentialStateCache._decode_event_member(item)["event_id"] for item in legacy_raw_page] == ["event-003", failed_event_id]
    assert await redis_client.exists(CredentialStateCache._event_dedupe_key(failed_event_id))


@pytest.mark.asyncio
async def test_concurrent_result_events_commit_before_cursor_can_advance(redis_client, monkeypatch):
    class CrossPodRedis:
        def __init__(self, client):
            self.client = client
            self.cas_conflicts = 0

        def __getattr__(self, name):
            return getattr(self.client, name)

        async def eval(self, script, numkeys, *args):
            result = await self.client.eval(script, numkeys, *args)
            if numkeys == 3 and int(result) == -1:
                self.cas_conflicts += 1
            return result

    cross_pod_redis = CrossPodRedis(redis_client)

    async def get_client():
        return cross_pod_redis

    monkeypatch.setattr(
        CredentialStateCache,
        "_get_or_create_pool",
        classmethod(lambda _cls: get_client()),
    )
    observed_at = "2026-08-14T00:00:00.123+00:00"
    event_ids = [f"concurrent-event-{index:03d}" for index in range(64)]

    await asyncio.gather(
        *(
            # 各调用模拟独立 Pod，不共享进程内锁，只由 Redis CAS 协调。
            CredentialStateCache._append_result_event({"event_id": event_id, "finished_at": observed_at})
            for event_id in event_ids
        )
    )

    # 直接按回滚后的旧排他时间游标逐页读取，所有并发提交均可达。
    legacy_cursor = ""
    observed_ids = []
    while True:
        minimum = f"({CredentialStateCache._event_score(legacy_cursor)}" if legacy_cursor else "-inf"
        raw_page = await redis_client.zrangebyscore(
            CredentialStateCache._event_stream_key(),
            min=minimum,
            max="+inf",
            start=0,
            num=7,
        )
        if not raw_page:
            break
        page = [CredentialStateCache._decode_event_member(item) for item in raw_page]
        observed_ids.extend(event["event_id"] for event in page)
        legacy_cursor = page[-1]["finished_at"]

    assert set(observed_ids) == set(event_ids)
    assert len(observed_ids) == len(event_ids)
    assert cross_pod_redis.cas_conflicts > 0


@pytest.mark.asyncio
async def test_rollback_cursor_keeps_old_writer_events_reachable(redis_client, monkeypatch):
    async def get_client():
        return redis_client

    monkeypatch.setattr(
        CredentialStateCache,
        "_get_or_create_pool",
        classmethod(lambda _cls: get_client()),
    )
    observed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    for index in range(64):
        await CredentialStateCache.append_result_event(
            {
                "event_id": f"new-writer-{index:03d}",
                "finished_at": observed_at,
            }
        )
    new_events = await CredentialStateCache.list_result_events(limit=64)
    await CredentialStateCache.set_push_cursor(CredentialStateCache.event_cursor(new_events[-1]))

    legacy_cursor = await redis_client.get(CredentialStateCache._push_cursor_key())
    old_writer_finished_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    old_writer_event = json.dumps(
        {
            "event_id": "old-writer-after-rollback",
            "finished_at": old_writer_finished_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    await redis_client.zadd(
        CredentialStateCache._event_stream_key(),
        {old_writer_event: CredentialStateCache._event_score(old_writer_finished_at)},
    )

    assert CredentialStateCache._event_score(legacy_cursor) < (CredentialStateCache._event_score(old_writer_finished_at))
    rollback_page = await redis_client.zrangebyscore(
        CredentialStateCache._event_stream_key(),
        min=f"({CredentialStateCache._event_score(legacy_cursor)}",
        max="+inf",
    )
    assert "old-writer-after-rollback" in {CredentialStateCache._decode_event_member(item)["event_id"] for item in rollback_page}


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
    stored_values = [str(await redis_client.get(key) or "") for key in keys]
    stored = " ".join(stored_values)
    assert "do-not-store-one" not in stored
    assert "do-not-store-two" not in stored


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
