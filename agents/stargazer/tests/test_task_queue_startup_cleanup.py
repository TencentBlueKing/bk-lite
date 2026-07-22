import asyncio
import fnmatch
import json
from unittest.mock import AsyncMock

import core.task_queue as task_queue_module
import pytest
from core.task_queue import TaskQueue
from core.task_queue_startup_cleanup import (
    LOCK_KEY,
    StartupCleanupConfig,
    StartupCleanupConfigError,
    StartupCleanupResult,
    cleanup_startup_orphan_markers,
)
from redis.exceptions import ResponseError
from sanic import Sanic


class FakeRedis:
    def __init__(
        self,
        *,
        strings=None,
        queue=None,
        lock_acquired=True,
        eval_errors=None,
        eval_results=None,
        get_errors=None,
        set_wait=None,
        release_wait=None,
    ):
        self.strings = dict(strings or {})
        self.queue = dict(queue or {})
        self.lock_acquired = lock_acquired
        self.eval_errors = set(eval_errors or ())
        self.eval_results = dict(eval_results or {})
        self.get_errors = dict(get_errors or {})
        self.set_wait = set_wait
        self.release_wait = release_wait
        self.scan_calls = []
        self.write_commands = []
        self.business_writes = []

    async def set(self, key, value, *, nx=False, ex=None):
        key = _as_bytes(key)
        value = _as_bytes(value)
        self.write_commands.append(("SET", key, value, nx, ex))
        if self.set_wait is not None:
            await self.set_wait.wait()
        if nx and (not self.lock_acquired or key in self.strings):
            return False
        self.strings[key] = value
        return True

    async def get(self, key):
        key = _as_bytes(key)
        error = self.get_errors.get(key)
        if error is not None:
            raise error
        return self.strings.get(key)

    async def exists(self, key):
        key = _as_bytes(key)
        return int(key in self.strings or key in self.queue)

    async def zscore(self, key, value):
        assert _as_bytes(key) == b"arq:queue"
        return self.queue.get(_as_bytes(value))

    async def scan_iter(self, *, match, count):
        assert count == 500
        pattern = _as_bytes(match)
        self.scan_calls.append(pattern)
        for key in sorted(tuple(self.strings)):
            if fnmatch.fnmatchcase(key.decode(), pattern.decode()):
                yield key

    async def eval(self, script, numkeys, *args):
        assert numkeys in {1, 3, 4}
        key = _as_bytes(args[0])
        if key in self.eval_errors:
            raise ResponseError("WRONGTYPE marker eval failed")

        if numkeys == 1:
            if self.release_wait is not None:
                await self.release_wait.wait()
            token = _as_bytes(args[1])
            if self.strings.get(key) == token:
                self.strings.pop(key)
                self.write_commands.append(("DEL", key))
                return 1
            return 0

        if key in self.eval_results:
            return self.eval_results[key]

        queue_key, in_progress_key = _as_bytes(args[1]), _as_bytes(args[2])
        if numkeys == 4:
            callback_context_key = _as_bytes(args[3])
            expected_job_id = _as_bytes(args[4])
            if _is_waiting_callback_context(
                self.strings.get(callback_context_key)
            ):
                return 0
        else:
            expected_job_id = _as_bytes(args[3])
        assert queue_key == b"arq:queue"
        if (
            self.strings.get(key) != expected_job_id
            or expected_job_id in self.queue
            or in_progress_key in self.strings
        ):
            return 0
        self.strings.pop(key)
        self.write_commands.append(("DEL", key))
        self.business_writes.append(("DEL", key))
        return 1


def _is_waiting_callback_context(value):
    if not value:
        return False
    context = json.loads(_as_bytes(value))
    return (context.get("status") or {}).get(
        "execution"
    ) == "waiting_callback" and context.get("callback_received_at") is None


def _callback_context(task_id):
    return json.dumps(
        {
            "status": {"execution": "waiting_callback"},
            "callback_received_at": None,
        }
    ).encode()


def _as_bytes(value):
    return value if isinstance(value, bytes) else str(value).encode()


@pytest.fixture
def fake_redis():
    return FakeRedis()


def test_startup_cleanup_config_uses_safe_defaults():
    config = StartupCleanupConfig.from_env({})

    assert config.enabled is True
    assert config.confirm_delay_seconds == 5
    assert config.max_markers == 10_000
    assert config.timeout_seconds == 30


def test_startup_cleanup_config_rejects_unsafe_direct_construction():
    with pytest.raises(StartupCleanupConfigError):
        StartupCleanupConfig(timeout_seconds=60, lock_ttl_seconds=60)


@pytest.mark.parametrize(
    "env",
    [
        {"TASK_QUEUE_STARTUP_ORPHAN_CONFIRM_DELAY_SECONDS": "-1"},
        {"TASK_QUEUE_STARTUP_ORPHAN_MAX_MARKERS": "0"},
        {"TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS": "not-a-number"},
        {"TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED": "sometimes"},
        {
            "TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS": "60",
            "TASK_QUEUE_STARTUP_ORPHAN_LOCK_TTL_SECONDS": "60",
        },
    ],
)
def test_startup_cleanup_config_rejects_unsafe_values(env):
    with pytest.raises(StartupCleanupConfigError):
        StartupCleanupConfig.from_env(env)


@pytest.mark.asyncio
async def test_cleanup_deletes_only_confirmed_orphan_markers(fake_redis):
    fake_redis.strings.update(
        {
            b"task:running:orphan": b"orphan-job",
            b"task:dedupe:queued": b"queued-job",
            b"task:running:active": b"active-job",
            b"credential:state:1": b"keep",
        }
    )
    fake_redis.queue[b"queued-job"] = 1000.0
    fake_redis.strings[b"arq:in-progress:active-job"] = b"1"

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=0),
    )

    assert result.deleted == 1
    assert b"task:running:orphan" not in fake_redis.strings
    assert b"task:dedupe:queued" in fake_redis.strings
    assert b"task:running:active" in fake_redis.strings
    assert fake_redis.strings[b"credential:state:1"] == b"keep"
    assert fake_redis.business_writes == [("DEL", b"task:running:orphan")]


@pytest.mark.asyncio
async def test_second_phase_preserves_marker_when_job_becomes_active(
    fake_redis,
):
    fake_redis.strings[b"task:dedupe:key"] = b"job-1"

    async def activate_during_delay(_seconds):
        fake_redis.queue[b"job-1"] = 2000.0

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=5),
        sleep=activate_during_delay,
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert b"task:dedupe:key" in fake_redis.strings


@pytest.mark.asyncio
async def test_second_phase_preserves_replaced_marker_value(fake_redis):
    fake_redis.strings[b"task:running:key"] = b"job-1"

    async def replace_during_delay(_seconds):
        fake_redis.strings[b"task:running:key"] = b"job-2"

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1),
        sleep=replace_during_delay,
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert fake_redis.strings[b"task:running:key"] == b"job-2"


@pytest.mark.asyncio
async def test_wrongtype_marker_is_preserved_and_reported_as_error(fake_redis):
    marker_key = b"task:running:invalid"
    fake_redis.strings[marker_key] = b"not-readable"
    fake_redis.get_errors[marker_key] = ResponseError("WRONGTYPE Operation")

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert result.preserved == 1
    assert marker_key in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_skips_when_maintenance_lock_is_not_acquired(fake_redis):
    fake_redis.lock_acquired = False
    fake_redis.strings[b"task:running:orphan"] = b"job-1"

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "skipped"
    assert result.reason == "lock_not_acquired"
    assert result.scanned == result.candidates == result.deleted == 0
    assert b"task:running:orphan" in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_stops_at_configured_scan_limit(fake_redis):
    fake_redis.strings.update(
        {
            b"task:running:1": b"job-1",
            b"task:running:2": b"job-2",
            b"task:running:3": b"job-3",
        }
    )

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=0, max_markers=2),
    )

    assert result.status == "warning"
    assert result.reason == "limit_reached"
    assert result.truncated is True
    assert result.scanned == 2
    assert result.deleted == 2
    assert b"task:running:3" in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_marks_limit_reached_even_when_scanned_marker_is_active(
    fake_redis,
):
    fake_redis.strings[b"task:running:active"] = b"job-1"
    fake_redis.queue[b"job-1"] = 1000.0

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=0, max_markers=1),
    )

    assert result.status == "warning"
    assert result.reason == "limit_reached"
    assert result.truncated is True
    assert result.scanned == 1
    assert result.candidates == 0


@pytest.mark.asyncio
async def test_cleanup_reports_timeout_and_releases_its_lock(fake_redis):
    fake_redis.strings[b"task:running:orphan"] = b"job-1"

    async def time_out(_seconds):
        raise asyncio.TimeoutError

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1, timeout_seconds=2),
        sleep=time_out,
    )

    assert result.status == "warning"
    assert result.reason == "timeout"
    assert b"task:running:orphan" in fake_redis.strings
    assert LOCK_KEY not in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_keeps_other_markers_when_single_marker_lua_errors(
    fake_redis,
):
    broken_marker = b"task:dedupe:broken"
    fake_redis.strings.update(
        {
            broken_marker: b"job-1",
            b"task:running:orphan": b"job-2",
        }
    )
    fake_redis.eval_errors.add(broken_marker)

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert result.deleted == 1
    assert broken_marker in fake_redis.strings
    assert b"task:running:orphan" not in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_releases_lock_only_when_its_token_still_matches(
    fake_redis,
):
    fake_redis.strings[b"task:running:orphan"] = b"job-1"

    async def replace_lock_during_delay(_seconds):
        fake_redis.strings[LOCK_KEY] = b"another-owner"

    await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1),
        sleep=replace_lock_during_delay,
    )

    assert fake_redis.strings[LOCK_KEY] == b"another-owner"


@pytest.mark.asyncio
async def test_cleanup_keeps_waiting_host_callback_marker(
    fake_redis,
):
    fake_redis.strings.update(
        {
            b"task:running:host-task": b"job-1",
            b"host_remote:callback_context:host-task": _callback_context(
                "host-task"
            ),
        }
    )

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert b"task:running:host-task" in fake_redis.strings


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_callback_context", [b"{", b"[]"])
async def test_bad_callback_context_preserves_only_its_running_marker(
    fake_redis,
    bad_callback_context,
):
    protected_marker = b"task:running:bad-context"
    safe_marker = b"task:dedupe:orphan"
    fake_redis.strings.update(
        {
            protected_marker: b"job-1",
            b"host_remote:callback_context:bad-context": bad_callback_context,
            safe_marker: b"job-2",
        }
    )

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert protected_marker in fake_redis.strings
    assert safe_marker not in fake_redis.strings


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
async def test_invalid_callback_execution_preserves_only_its_running_marker(
    fake_redis,
    bad_callback_context,
):
    protected_marker = b"task:running:bad-execution"
    callback_context_key = b"host_remote:callback_context:bad-execution"
    safe_marker = b"task:dedupe:orphan"
    fake_redis.strings.update(
        {
            protected_marker: b"job-1",
            callback_context_key: bad_callback_context,
            safe_marker: b"job-2",
        }
    )

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert protected_marker in fake_redis.strings
    assert safe_marker not in fake_redis.strings


@pytest.mark.asyncio
async def test_invalid_lua_callback_result_is_preserved_and_reported():
    protected_marker = b"task:running:bad-confirmation"
    safe_marker = b"task:dedupe:orphan"
    redis = FakeRedis(
        strings={protected_marker: b"job-1", safe_marker: b"job-2"},
        eval_results={protected_marker: -1},
    )

    result = await cleanup_startup_orphan_markers(
        redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert result.deleted == 1
    assert protected_marker in redis.strings
    assert safe_marker not in redis.strings


@pytest.mark.asyncio
async def test_second_phase_preserves_running_marker_when_callback_appears(
    fake_redis,
):
    fake_redis.strings[b"task:running:host-task"] = b"job-1"

    async def create_callback_during_delay(_seconds):
        fake_redis.strings[
            b"host_remote:callback_context:host-task"
        ] = _callback_context("host-task")

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1),
        sleep=create_callback_during_delay,
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert b"task:running:host-task" in fake_redis.strings


@pytest.mark.asyncio
async def test_second_phase_preserves_marker_when_job_becomes_in_progress(
    fake_redis,
):
    fake_redis.strings[b"task:running:task-1"] = b"job-1"

    async def begin_processing_during_delay(_seconds):
        fake_redis.strings[b"arq:in-progress:job-1"] = b"1"

    result = await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1),
        sleep=begin_processing_during_delay,
    )

    assert result.deleted == 0
    assert result.preserved == 1
    assert b"task:running:task-1" in fake_redis.strings


@pytest.mark.asyncio
async def test_cleanup_times_out_while_lock_acquisition_is_actually_blocked():
    redis = FakeRedis(set_wait=asyncio.Event())

    result = await asyncio.wait_for(
        cleanup_startup_orphan_markers(
            redis,
            StartupCleanupConfig(
                confirm_delay_seconds=0,
                timeout_seconds=0.01,
                lock_ttl_seconds=1,
            ),
        ),
        timeout=0.2,
    )

    assert result.status == "warning"
    assert result.reason == "timeout"


@pytest.mark.asyncio
async def test_cleanup_times_out_when_lock_release_is_actually_blocked():
    redis = FakeRedis(release_wait=asyncio.Event())

    result = await asyncio.wait_for(
        cleanup_startup_orphan_markers(
            redis,
            StartupCleanupConfig(
                confirm_delay_seconds=0,
                timeout_seconds=0.01,
                lock_ttl_seconds=1,
            ),
        ),
        timeout=0.2,
    )

    assert result.status == "warning"
    assert result.reason == "timeout"


@pytest.mark.asyncio
async def test_lock_release_failure_does_not_block_cleanup_result():
    redis = FakeRedis(eval_errors={LOCK_KEY})

    result = await cleanup_startup_orphan_markers(
        redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "success"
    assert result.reason is None


@pytest.mark.asyncio
async def test_wrongtype_marker_does_not_stop_other_safe_marker_cleanup(
    fake_redis,
):
    broken_key = b"task:dedupe:broken"
    fake_redis.strings.update(
        {
            broken_key: b"wrongtype",
            b"task:running:orphan": b"job-2",
        }
    )
    fake_redis.get_errors[broken_key] = ResponseError("WRONGTYPE Operation")

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert broken_key in fake_redis.strings
    assert b"task:running:orphan" not in fake_redis.strings


@pytest.mark.asyncio
async def test_redis_connection_error_is_not_misclassified_as_marker_error(
    fake_redis,
):
    marker_key = b"task:running:unavailable"
    fake_redis.strings[marker_key] = b"job-1"
    fake_redis.get_errors[marker_key] = ConnectionError("redis unavailable")

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await cleanup_startup_orphan_markers(
            fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
        )


def _listener(app, event, name):
    return next(
        item.listener
        for item in app._future_listeners
        if item.event == event and item.listener.__name__ == name
    )


def test_task_queue_registers_non_blocking_startup_cleanup_listener():
    app = Sanic("StartupCleanupLifecycle")
    queue = TaskQueue(app)

    listeners = {
        (listener.event, listener.listener.__name__)
        for listener in app._future_listeners
    }

    assert ("after_server_start", "start_orphan_cleanup") in listeners
    assert ("after_server_stop", "stop_task_queue") in listeners
    assert queue._startup_cleanup_task is None


@pytest.mark.asyncio
async def test_start_listener_schedules_without_waiting(monkeypatch):
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupNonBlocking")
    queue = TaskQueue(app)
    queue.pool = AsyncMock()

    async def cleanup(*_args, **_kwargs):
        await blocker.wait()

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )

    assert queue._startup_cleanup_task is not None
    assert not queue._startup_cleanup_task.done()

    await _listener(app, "after_server_stop", "stop_task_queue")(app, None)


@pytest.mark.asyncio
async def test_start_listener_does_not_create_task_when_cleanup_is_disabled(
    monkeypatch,
):
    monkeypatch.setenv("TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED", "false")
    app = Sanic("StartupCleanupDisabled")
    queue = TaskQueue(app)

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )

    assert queue._startup_cleanup_task is None


@pytest.mark.asyncio
async def test_start_listener_invalid_config_is_fail_open_and_redacted(
    monkeypatch, caplog
):
    app = Sanic("StartupCleanupInvalidConfig")
    queue = TaskQueue(app)

    def invalid_config():
        raise StartupCleanupConfigError("job-123 redis://:password@redis/0")

    monkeypatch.setattr(
        task_queue_module.StartupCleanupConfig,
        "from_env",
        staticmethod(invalid_config),
    )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )

    assert queue._startup_cleanup_task is None
    assert "event=task_queue_startup_cleanup status=warning" in caplog.text
    assert "reason=invalid_config" in caplog.text
    assert "job-123" not in caplog.text
    assert "password" not in caplog.text
    assert "redis://" not in caplog.text


@pytest.mark.asyncio
async def test_startup_cleanup_background_error_is_redacted(
    monkeypatch, caplog
):
    app = Sanic("StartupCleanupRedactedFailure")
    queue = TaskQueue(app)

    async def cleanup(*_args, **_kwargs):
        raise RuntimeError("job-123 redis://:password@redis/0")

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert "event=task_queue_startup_cleanup status=warning" in caplog.text
    assert "reason=cleanup_failed" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "job-123" not in caplog.text
    assert "password" not in caplog.text
    assert "redis://" not in caplog.text


@pytest.mark.asyncio
async def test_startup_cleanup_success_log_contains_only_safe_result_counts(
    monkeypatch, caplog
):
    app = Sanic("StartupCleanupSafeSuccessLog")
    queue = TaskQueue(app)

    async def cleanup(*_args, **_kwargs):
        return StartupCleanupResult(
            status="success",
            reason=None,
            scanned=3,
            candidates=2,
            deleted=1,
            preserved=1,
            errors=0,
            truncated=False,
        )

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert "event=task_queue_startup_cleanup status=success" in caplog.text
    assert (
        "scanned=3 candidates=2 deleted=1 preserved=1 errors=0" in caplog.text
    )


@pytest.mark.asyncio
async def test_stop_listener_awaits_cleanup_before_pool_close(
    monkeypatch,
):
    started = asyncio.Event()
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupStop")
    queue = TaskQueue(app)
    queue.pool = AsyncMock()

    async def cleanup(*_args, **_kwargs):
        started.set()
        await blocker.wait()

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await started.wait()
    cleanup_task = queue._startup_cleanup_task

    await _listener(app, "after_server_stop", "stop_task_queue")(app, None)

    assert cleanup_task.cancelled()
    assert queue.pool is None


@pytest.mark.asyncio
async def test_start_listener_returns_within_bound_while_cleanup_is_blocked(
    monkeypatch,
):
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupBoundedListener")
    queue = TaskQueue(app)
    queue.pool = AsyncMock()

    async def cleanup(*_args, **_kwargs):
        await blocker.wait()

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )

    await asyncio.wait_for(
        _listener(app, "after_server_start", "start_orphan_cleanup")(
            app, None
        ),
        timeout=0.05,
    )

    await _listener(app, "after_server_stop", "stop_task_queue")(app, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["invalid_config", "disabled"])
async def test_start_listener_remains_fail_open_when_its_logger_raises(
    monkeypatch, mode
):
    app = Sanic(f"StartupCleanupLoggerStart{mode}")
    queue = TaskQueue(app)

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr(task_queue_module.logger, "warning", fail_log)
    monkeypatch.setattr(task_queue_module.logger, "info", fail_log)
    if mode == "invalid_config":
        monkeypatch.setattr(
            task_queue_module.StartupCleanupConfig,
            "from_env",
            staticmethod(
                lambda: (_ for _ in ()).throw(StartupCleanupConfigError())
            ),
        )
    else:
        monkeypatch.setenv(
            "TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED", "false"
        )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )

    assert queue._startup_cleanup_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        StartupCleanupResult("success", None, 1, 0, 0, 1, 0, False),
        StartupCleanupResult(
            "skipped", "lock_not_acquired", 0, 0, 0, 0, 0, False
        ),
        StartupCleanupResult("warning", "timeout", 1, 1, 0, 1, 0, False),
        StartupCleanupResult("warning", "marker_errors", 1, 1, 0, 1, 1, False),
    ],
    ids=["success", "locked", "timeout", "warning"],
)
async def test_background_result_logging_failure_is_consumed(
    monkeypatch, result
):
    app = Sanic(f"StartupCleanupLoggerResult{result.status}{result.reason}")
    queue = TaskQueue(app)

    async def cleanup(*_args, **_kwargs):
        return result

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "warning", fail_log)
    monkeypatch.setattr(task_queue_module.logger, "info", fail_log)

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task
    assert queue._startup_cleanup_task.done()
    assert queue._startup_cleanup_task.exception() is None


@pytest.mark.asyncio
async def test_background_exception_logging_failure_is_consumed(monkeypatch):
    app = Sanic("StartupCleanupLoggerException")
    queue = TaskQueue(app)

    async def cleanup(*_args, **_kwargs):
        raise RuntimeError("cleanup unavailable")

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "warning", fail_log)

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task
    assert queue._startup_cleanup_task.done()
    assert queue._startup_cleanup_task.exception() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_level", "expected_message"),
    [
        (
            StartupCleanupResult("success", None, 1, 0, 0, 1, 0, False),
            "info",
            "event=task_queue_startup_cleanup status=success "
            "scanned=1 candidates=0 deleted=0 preserved=1 errors=0 "
            "truncated=False",
        ),
        (
            StartupCleanupResult(
                "skipped", "lock_not_acquired", 0, 0, 0, 0, 0, False
            ),
            "info",
            "event=task_queue_startup_cleanup status=skipped "
            "reason=lock_not_acquired scanned=0 candidates=0 deleted=0 "
            "preserved=0 errors=0 truncated=False",
        ),
        (
            StartupCleanupResult("warning", "timeout", 1, 1, 0, 1, 0, False),
            "warning",
            "event=task_queue_startup_cleanup status=warning reason=timeout "
            "scanned=1 candidates=1 deleted=0 preserved=1 errors=0 "
            "truncated=False",
        ),
        (
            StartupCleanupResult(
                "warning", "marker_errors", 1, 1, 0, 1, 1, False
            ),
            "warning",
            "event=task_queue_startup_cleanup status=warning "
            "reason=marker_errors scanned=1 candidates=1 deleted=0 "
            "preserved=1 errors=1 truncated=False",
        ),
    ],
    ids=["success", "locked", "timeout", "marker_errors"],
)
async def test_background_result_logs_only_its_safe_legal_mapping(
    monkeypatch, result, expected_level, expected_message
):
    app = Sanic(f"StartupCleanupLogMapping{expected_level}{result.reason}")
    queue = TaskQueue(app)
    records = []

    async def cleanup(*_args, **_kwargs):
        return result

    def record(level):
        def log(message, *args):
            records.append((level, message % args if args else message))

        return log

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "info", record("info"))
    monkeypatch.setattr(task_queue_module.logger, "warning", record("warning"))

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert records == [(expected_level, expected_message)]
    for secret in (
        "job-123",
        "task:running:secret",
        "redis://:password@redis/0",
        "raw exception message",
    ):
        assert secret not in records[0][1]


@pytest.mark.asyncio
async def test_illegal_result_status_reason_pair_is_downgraded(monkeypatch):
    app = Sanic("StartupCleanupIllegalResultPair")
    queue = TaskQueue(app)
    records = []

    async def cleanup(*_args, **_kwargs):
        return StartupCleanupResult("success", "timeout", 0, 0, 0, 0, 0, False)

    def record(level):
        def log(message, *args):
            records.append((level, message % args if args else message))

        return log

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "info", record("info"))
    monkeypatch.setattr(task_queue_module.logger, "warning", record("warning"))

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert records == [
        (
            "warning",
            "event=task_queue_startup_cleanup status=warning "
            "reason=unknown_result scanned=0 candidates=0 deleted=0 "
            "preserved=0 errors=0 truncated=False",
        )
    ]


@pytest.mark.asyncio
async def test_background_exception_log_excludes_sensitive_exception_text(
    monkeypatch,
):
    app = Sanic("StartupCleanupExceptionLogRedaction")
    queue = TaskQueue(app)
    records = []

    async def cleanup(*_args, **_kwargs):
        raise RuntimeError(
            "job-123 task:running:secret redis://:password@redis/0 "
            "raw exception message"
        )

    def record(message, *args):
        records.append(message % args if args else message)

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "warning", record)

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert records == [
        "event=task_queue_startup_cleanup status=warning "
        "reason=cleanup_failed exception_type=RuntimeError"
    ]


@pytest.mark.asyncio
async def test_stop_closes_pool_after_cleanup_even_when_logger_raises(
    monkeypatch,
):
    events = []
    cleanup_started = asyncio.Event()
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupLoggerStop")
    queue = TaskQueue(app)

    class Pool:
        async def close(self):
            events.append("pool_closed")

    async def cleanup(*_args, **_kwargs):
        cleanup_started.set()
        try:
            await blocker.wait()
        finally:
            events.append("cleanup_finished")

    def fail_log(*_args, **_kwargs):
        raise RuntimeError("logger unavailable")

    queue.pool = Pool()
    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    monkeypatch.setattr(task_queue_module.logger, "warning", fail_log)
    monkeypatch.setattr(task_queue_module.logger, "info", fail_log)
    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await cleanup_started.wait()

    await _listener(app, "after_server_stop", "stop_task_queue")(app, None)

    assert events == ["cleanup_finished", "pool_closed"]
    assert queue.pool is None


@pytest.mark.asyncio
async def test_stop_reraises_external_cancellation_after_cleanup(monkeypatch):
    events = []
    cleanup_started = asyncio.Event()
    close_started = asyncio.Event()
    allow_close = asyncio.Event()
    app = Sanic("StartupCleanupExternalCancellation")
    queue = TaskQueue(app)

    class Pool:
        async def close(self):
            close_started.set()
            await allow_close.wait()
            events.append("pool_closed")

    async def cleanup(*_args, **_kwargs):
        cleanup_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("cleanup_finished")

    queue.pool = Pool()
    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await cleanup_started.wait()

    stop_task = asyncio.create_task(
        _listener(app, "after_server_stop", "stop_task_queue")(app, None)
    )
    await close_started.wait()
    stop_task.cancel()
    allow_close.set()

    with pytest.raises(asyncio.CancelledError):
        await stop_task

    assert events == ["cleanup_finished", "pool_closed"]
    assert queue.pool is None


@pytest.mark.asyncio
async def test_repeated_start_listener_keeps_running_cleanup_task(monkeypatch):
    started = asyncio.Event()
    blocker = asyncio.Event()
    app = Sanic("StartupCleanupRepeatedStart")
    queue = TaskQueue(app)
    queue.pool = AsyncMock()
    calls = 0

    async def cleanup(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await blocker.wait()

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    start_listener = _listener(
        app, "after_server_start", "start_orphan_cleanup"
    )

    await start_listener(app, None)
    await started.wait()
    first_task = queue._startup_cleanup_task
    await start_listener(app, None)

    assert calls == 1
    assert queue._startup_cleanup_task is first_task

    await _listener(app, "after_server_stop", "stop_task_queue")(app, None)
    assert first_task.cancelled()


@pytest.mark.asyncio
async def test_completed_cleanup_task_is_consumed_before_restart(monkeypatch):
    app = Sanic("StartupCleanupCompletedRestart")
    queue = TaskQueue(app)
    calls = 0

    async def cleanup(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return StartupCleanupResult("success", None, 0, 0, 0, 0, 0, False)

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )
    start_listener = _listener(
        app, "after_server_start", "start_orphan_cleanup"
    )

    await start_listener(app, None)
    first_task = queue._startup_cleanup_task
    await first_task
    await start_listener(app, None)
    await queue._startup_cleanup_task

    assert calls == 2
    assert queue._startup_cleanup_task is not first_task


@pytest.mark.asyncio
async def test_unknown_cleanup_result_fields_are_downgraded_to_safe_values(
    monkeypatch, caplog
):
    app = Sanic("StartupCleanupUnknownResult")
    queue = TaskQueue(app)

    async def cleanup(*_args, **_kwargs):
        return StartupCleanupResult(
            status=["unexpected"],
            reason="task:running:secret-job",
            scanned=0,
            candidates=0,
            deleted=0,
            preserved=0,
            errors=0,
            truncated=False,
        )

    monkeypatch.setattr(
        task_queue_module, "cleanup_startup_orphan_markers", cleanup
    )

    await _listener(app, "after_server_start", "start_orphan_cleanup")(
        app, None
    )
    await queue._startup_cleanup_task

    assert "status=warning reason=unknown_result" in caplog.text
    assert "task:running:secret-job" not in caplog.text
