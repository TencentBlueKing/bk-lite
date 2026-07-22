import asyncio
import fnmatch

import pytest

from core.task_queue_startup_cleanup import (
    LOCK_KEY,
    StartupCleanupConfig,
    StartupCleanupConfigError,
    cleanup_startup_orphan_markers,
)


class FakeRedis:
    def __init__(
        self, *, strings=None, queue=None, lock_acquired=True, eval_errors=None
    ):
        self.strings = dict(strings or {})
        self.queue = dict(queue or {})
        self.lock_acquired = lock_acquired
        self.eval_errors = set(eval_errors or ())
        self.scan_calls = []
        self.write_commands = []
        self.business_writes = []

    async def set(self, key, value, *, nx=False, ex=None):
        key = _as_bytes(key)
        value = _as_bytes(value)
        self.write_commands.append(("SET", key, value, nx, ex))
        if nx and (not self.lock_acquired or key in self.strings):
            return False
        self.strings[key] = value
        return True

    async def get(self, key):
        return self.strings.get(_as_bytes(key))

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
        assert numkeys in {1, 3}
        key = _as_bytes(args[0])
        if key in self.eval_errors:
            raise RuntimeError("marker eval failed")

        if numkeys == 1:
            token = _as_bytes(args[1])
            if self.strings.get(key) == token:
                self.strings.pop(key)
                self.write_commands.append(("DEL", key))
                return 1
            return 0

        queue_key, in_progress_key, expected_job_id = (
            _as_bytes(args[1]),
            _as_bytes(args[2]),
            _as_bytes(args[3]),
        )
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
async def test_second_phase_preserves_marker_when_job_becomes_active(fake_redis):
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
async def test_non_string_marker_is_preserved_and_reported_as_error(fake_redis):
    fake_redis.strings[b"task:running:invalid"] = 123

    result = await cleanup_startup_orphan_markers(
        fake_redis, StartupCleanupConfig(confirm_delay_seconds=0)
    )

    assert result.status == "warning"
    assert result.reason == "marker_errors"
    assert result.errors == 1
    assert result.preserved == 1
    assert b"task:running:invalid" in fake_redis.strings


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
async def test_cleanup_keeps_other_markers_when_single_marker_lua_errors(fake_redis):
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
async def test_cleanup_releases_lock_only_when_its_token_still_matches(fake_redis):
    fake_redis.strings[b"task:running:orphan"] = b"job-1"

    async def replace_lock_during_delay(_seconds):
        fake_redis.strings[LOCK_KEY] = b"another-owner"

    await cleanup_startup_orphan_markers(
        fake_redis,
        StartupCleanupConfig(confirm_delay_seconds=1),
        sleep=replace_lock_during_delay,
    )

    assert fake_redis.strings[LOCK_KEY] == b"another-owner"
