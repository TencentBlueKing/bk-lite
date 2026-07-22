import asyncio
import base64
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
import pytest_asyncio
from core.task_queue_cleanup import (
    CleanupRestoreError,
    _payload_digest,
    backup_and_apply_cleanup,
    build_cleanup_plan,
    restore_cleanup_backup,
)
from core.task_queue_startup_cleanup import (
    _RELEASE_LOCK_LUA,
    LOCK_KEY,
    StartupCleanupConfig,
    cleanup_startup_orphan_markers,
)
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError


def test_redis_server_cleanup_kills_after_terminated_process_times_out():
    process = Mock()
    process.poll.return_value = None
    process.communicate.side_effect = subprocess.TimeoutExpired(
        "redis-server", 5
    )

    _stop_redis_server(process)

    process.terminate.assert_called_once_with()
    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=5)


def _stop_redis_server(process) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture
def redis_server_socket(tmp_path):
    redis_server = shutil.which("redis-server")
    if redis_server is None:
        pytest.skip("redis-server is not installed")

    socket_path = Path("/tmp") / (
        f"stargazer-redis-{secrets.token_hex(6)}.sock"
    )
    process = subprocess.Popen(
        [
            redis_server,
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
    probe = Redis(
        unix_socket_path=str(socket_path),
        db=15,
        decode_responses=False,
    )
    try:
        last_connection_error = None
        for _attempt in range(100):
            try:
                if probe.ping():
                    break
            except (RedisConnectionError, OSError) as error:
                last_connection_error = error
                time.sleep(0.01)
        else:
            return_code = process.poll()
            diagnostics = (
                process.stderr.read() if return_code is not None else ""
            )
            pytest.fail(
                "temporary redis-server did not start: "
                f"socket={socket_path} returncode={return_code} "
                f"last_connection_error={last_connection_error!r} "
                f"stderr={diagnostics}"
            )
        yield socket_path
    finally:
        probe.close()
        try:
            _stop_redis_server(process)
        finally:
            socket_path.unlink(missing_ok=True)


@pytest.fixture
def real_redis(redis_server_socket):
    client = Redis(
        unix_socket_path=str(redis_server_socket),
        db=15,
        decode_responses=False,
    )
    try:
        client.flushdb()
        yield client
    finally:
        try:
            client.flushdb()
        finally:
            client.close()


@pytest_asyncio.fixture
async def real_async_redis(redis_server_socket):
    client = AsyncRedis(
        unix_socket_path=str(redis_server_socket),
        db=15,
        decode_responses=False,
    )
    try:
        await client.flushdb()
        yield client
    finally:
        try:
            await client.flushdb()
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_second_phase_preserves_reactivated_job(
    real_async_redis,
):
    await real_async_redis.set(b"task:dedupe:key", b"job-1", ex=600)

    async def reactivate(_seconds):
        await real_async_redis.zadd(b"arq:queue", {b"job-1": 1000.0})

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=reactivate,
    )

    assert result.deleted == 0
    assert await real_async_redis.get(b"task:dedupe:key") == b"job-1"


@pytest.mark.asyncio
async def test_real_redis_two_replicas_only_one_runs_cleanup(real_async_redis):
    await real_async_redis.set(b"task:dedupe:orphan", b"job-1", ex=600)
    second_client = AsyncRedis(
        unix_socket_path=real_async_redis.connection_pool.connection_kwargs[
            "path"
        ],
        db=15,
        decode_responses=False,
    )
    entered_confirmation = asyncio.Event()
    release_confirmation = asyncio.Event()

    async def wait_for_confirmation(_seconds):
        entered_confirmation.set()
        await release_confirmation.wait()

    first = asyncio.create_task(
        cleanup_startup_orphan_markers(
            real_async_redis,
            StartupCleanupConfig(confirm_delay_seconds=5),
            sleep=wait_for_confirmation,
        )
    )
    await asyncio.wait_for(entered_confirmation.wait(), timeout=1)
    try:
        second = await cleanup_startup_orphan_markers(
            second_client,
            StartupCleanupConfig(confirm_delay_seconds=0),
        )
        release_confirmation.set()
        first_result = await first
    finally:
        release_confirmation.set()
        await second_client.aclose()

    assert first_result.deleted == 1
    assert second.status == "skipped"
    assert second.reason == "lock_not_acquired"


@pytest.mark.asyncio
async def test_real_redis_second_phase_preserves_replaced_marker_value(
    real_async_redis,
):
    marker_key = b"task:running:task-1"
    await real_async_redis.set(marker_key, b"job-1", ex=600)

    async def replace_marker(_seconds):
        await real_async_redis.set(marker_key, b"job-2", ex=600)

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=replace_marker,
    )

    assert result.deleted == 0
    assert await real_async_redis.get(marker_key) == b"job-2"


@pytest.mark.asyncio
@pytest.mark.parametrize("activation", ["queue", "in_progress", "callback"])
async def test_real_redis_second_phase_preserves_marker_that_becomes_active(
    real_async_redis,
    activation,
):
    marker_key = b"task:running:task-1"
    await real_async_redis.set(marker_key, b"job-1", ex=600)

    async def activate(_seconds):
        if activation == "queue":
            await real_async_redis.zadd(b"arq:queue", {b"job-1": 1000.0})
        elif activation == "in_progress":
            await real_async_redis.set(b"arq:in-progress:job-1", b"1")
        else:
            await real_async_redis.set(
                b"host_remote:callback_context:task-1",
                json.dumps(
                    {
                        "status": {"execution": "waiting_callback"},
                        "callback_received_at": None,
                    }
                ).encode(),
            )

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=activate,
    )

    assert result.deleted == 0
    assert await real_async_redis.get(marker_key) == b"job-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_callback_context", [b"{", b"[]"])
async def test_real_redis_lua_preserves_marker_when_callback_becomes_invalid(
    real_async_redis,
    bad_callback_context,
):
    marker_key = b"task:running:task-1"
    await real_async_redis.set(marker_key, b"job-1", ex=600)

    async def corrupt_callback_context(_seconds):
        await real_async_redis.set(
            b"host_remote:callback_context:task-1",
            bad_callback_context,
        )

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=corrupt_callback_context,
    )

    assert result.deleted == 0
    assert await real_async_redis.get(marker_key) == b"job-1"


@pytest.mark.asyncio
async def test_real_redis_lua_only_deletes_confirmed_marker(real_async_redis):
    marker_key = b"task:running:orphan"
    await real_async_redis.set(marker_key, b"job-1", ex=600)
    await real_async_redis.set(b"arq:job:job-1", b"serialized-job", ex=600)
    await real_async_redis.set(b"arq:result:job-1", b"result", ex=600)
    await real_async_redis.set(b"arq:retry:job-1", b"1", ex=600)

    result = await cleanup_startup_orphan_markers(
        real_async_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.deleted == 1
    assert await real_async_redis.get(marker_key) is None
    assert await real_async_redis.get(b"arq:job:job-1") == b"serialized-job"
    assert await real_async_redis.get(b"arq:result:job-1") == b"result"
    assert await real_async_redis.get(b"arq:retry:job-1") == b"1"


@pytest.mark.asyncio
async def test_real_redis_non_owner_token_cannot_release_cleanup_lock(
    real_async_redis,
):
    owner_token = b"owner"
    await real_async_redis.set(LOCK_KEY, owner_token, ex=60)

    released = await real_async_redis.eval(
        _RELEASE_LOCK_LUA, 1, LOCK_KEY, b"other-owner"
    )

    assert released == 0
    assert await real_async_redis.get(LOCK_KEY) == owner_token


@pytest.mark.asyncio
async def test_real_redis_wrongtype_marker_preserves_it_and_continues(
    real_async_redis,
):
    broken_marker = b"task:running:broken"
    safe_marker = b"task:dedupe:orphan"
    await real_async_redis.rpush(broken_marker, b"not-a-string")
    await real_async_redis.set(safe_marker, b"job-1", ex=600)

    result = await cleanup_startup_orphan_markers(
        real_async_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert await real_async_redis.type(broken_marker) == b"list"
    assert await real_async_redis.get(safe_marker) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_callback_context", [b"{", b"[]"])
async def test_real_redis_bad_callback_context_preserves_only_that_marker(
    real_async_redis,
    bad_callback_context,
):
    protected_marker = b"task:running:bad-context"
    safe_marker = b"task:dedupe:orphan"
    await real_async_redis.set(protected_marker, b"job-1", ex=600)
    await real_async_redis.set(
        b"host_remote:callback_context:bad-context",
        bad_callback_context,
    )
    await real_async_redis.set(safe_marker, b"job-2", ex=600)

    result = await cleanup_startup_orphan_markers(
        real_async_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert await real_async_redis.get(protected_marker) == b"job-1"
    assert await real_async_redis.get(safe_marker) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_callback_context",
    [
        b'{"status":{"execution":"unknown"}}',
        b'{"status":{"execution":1}}',
        b'{"status":[]}',
        b'{"status":{}}',
        b"[]",
        b"null",
        b"\xff",
    ],
)
async def test_real_redis_invalid_callback_execution_preserves_only_its_marker(
    real_async_redis,
    bad_callback_context,
):
    protected_marker = b"task:running:bad-execution"
    safe_marker = b"task:dedupe:orphan"
    await real_async_redis.set(protected_marker, b"job-1", ex=600)
    await real_async_redis.set(
        b"host_remote:callback_context:bad-execution",
        bad_callback_context,
    )
    await real_async_redis.set(safe_marker, b"job-2", ex=600)

    result = await cleanup_startup_orphan_markers(
        real_async_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert await real_async_redis.get(protected_marker) == b"job-1"
    assert await real_async_redis.get(safe_marker) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_callback_context",
    [
        b'{"status":{"execution":"unknown"}}',
        b'{"status":{"execution":1}}',
        b'{"status":[]}',
        b'{"status":{}}',
        b"[]",
        b"null",
        b"\xff",
    ],
)
async def test_real_redis_lua_reports_invalid_callback_context(
    real_async_redis,
    bad_callback_context,
):
    protected_marker = b"task:running:bad-confirmation"
    safe_marker = b"task:dedupe:orphan"
    await real_async_redis.set(protected_marker, b"job-1", ex=600)
    await real_async_redis.set(safe_marker, b"job-2", ex=600)

    async def corrupt_callback_context(_seconds):
        await real_async_redis.set(
            b"host_remote:callback_context:bad-confirmation",
            bad_callback_context,
        )

    result = await cleanup_startup_orphan_markers(
        real_async_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=corrupt_callback_context,
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert await real_async_redis.get(protected_marker) == b"job-1"
    assert await real_async_redis.get(safe_marker) is None


def test_real_redis_cleanup_backup_and_restore_round_trip(
    real_redis,
    tmp_path,
):
    job_id = b"real-job"
    marker_key = b"task:running:real-task"
    job_key = b"arq:job:real-job"
    retry_key = b"arq:retry:real-job"
    real_redis.zadd(b"arq:queue", {job_id: 1234.5})
    real_redis.set(marker_key, job_id, px=90_000)
    real_redis.set(job_key, b"serialized-real-job", px=80_000)
    real_redis.set(retry_key, b"2", px=70_000)

    plan = build_cleanup_plan(
        real_redis, all_pending=False, include_in_progress=False
    )
    backup_path, cleanup_result = backup_and_apply_cleanup(
        real_redis,
        plan,
        backup_dir=tmp_path / "backups",
        redis_db=15,
    )

    assert cleanup_result.deleted_job_count == 1
    assert real_redis.zscore(b"arq:queue", job_id) is None
    assert real_redis.mget(marker_key, job_key, retry_key) == [None] * 3

    restore_result = restore_cleanup_backup(
        real_redis, backup_path=backup_path, redis_db=15
    )

    assert restore_result.restored_key_count == 3
    assert restore_result.restored_queue_job_count == 1
    assert real_redis.zscore(b"arq:queue", job_id) == 1234.5
    assert real_redis.mget(marker_key, job_key, retry_key) == [
        job_id,
        b"serialized-real-job",
        b"2",
    ]
    assert 0 < real_redis.pttl(marker_key) <= 90_000
    assert 0 < real_redis.pttl(job_key) <= 80_000
    assert 0 < real_redis.pttl(retry_key) <= 70_000


def test_damaged_dump_leaves_target_namespace_untouched(
    real_redis,
    tmp_path,
):
    job_id = b"damaged-job"
    marker_key = b"task:running:damaged-task"
    job_key = b"arq:job:damaged-job"
    real_redis.zadd(b"arq:queue", {job_id: 5678.0})
    real_redis.set(marker_key, job_id, px=90_000)
    real_redis.set(job_key, b"serialized-damaged-job", px=80_000)
    plan = build_cleanup_plan(
        real_redis, all_pending=False, include_in_progress=False
    )
    backup_path, _result = backup_and_apply_cleanup(
        real_redis,
        plan,
        backup_dir=tmp_path / "backups",
        redis_db=15,
    )
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    payload["keys"][marker_key.decode()]["dump"] = base64.b64encode(
        b"not-a-valid-redis-dump"
    ).decode()
    payload["content_sha256"] = _payload_digest(payload)
    backup_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CleanupRestoreError):
        restore_cleanup_backup(
            real_redis, backup_path=backup_path, redis_db=15
        )

    assert real_redis.zscore(b"arq:queue", job_id) is None
    assert real_redis.mget(marker_key, job_key) == [None, None]
    assert (
        list(real_redis.scan_iter(match=b"stargazer:task-queue-restore:tmp:*"))
        == []
    )
