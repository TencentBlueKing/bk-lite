import fnmatch
import json
import os
import stat
from unittest.mock import Mock

import pytest
from core.task_queue_cleanup import (
    CleanupBackupError,
    CleanupDriftError,
    CleanupStateError,
    apply_cleanup_plan,
    build_cleanup_plan,
    create_cleanup_backup,
)
from redis.exceptions import WatchError


class FakeRedis:
    def __init__(
        self,
        *,
        queue=None,
        strings=None,
        type_overrides=None,
        watch_error=False,
    ):
        self.queue = dict(queue or {})
        self.strings = dict(strings or {})
        self.type_overrides = dict(type_overrides or {})
        self.watch_error = watch_error
        self.scan_patterns = []
        self.keys_calls = 0
        self.write_calls = []
        self.committed_writes = []

    def type(self, key):
        key = _as_bytes(key)
        if key in self.type_overrides:
            return self.type_overrides[key]
        if key == b"arq:queue":
            return b"zset" if self.queue else b"none"
        if key in self.strings:
            return b"string"
        return b"none"

    def zrange(self, key, start, end, *, withscores=False):
        assert _as_bytes(key) == b"arq:queue"
        items = sorted(self.queue.items(), key=lambda item: (item[1], item[0]))
        if withscores:
            return items
        return [job_id for job_id, _score in items]

    def scan_iter(self, *, match, count):
        assert count == 500
        pattern = _as_bytes(match)
        self.scan_patterns.append(pattern)
        for key in sorted(self.strings):
            if fnmatch.fnmatchcase(key.decode(), pattern.decode()):
                yield key

    def get(self, key):
        return self.strings.get(_as_bytes(key))

    def exists(self, key):
        key = _as_bytes(key)
        return int(key in self.strings or key in self.queue)

    def zscore(self, key, value):
        assert _as_bytes(key) == b"arq:queue"
        return self.queue.get(_as_bytes(value))

    def zcard(self, key):
        assert _as_bytes(key) == b"arq:queue"
        return len(self.queue)

    def dump(self, key):
        key = _as_bytes(key)
        if key in self.strings:
            return b"redis-dump:" + key
        return None

    def pttl(self, key):
        return 60_000 if _as_bytes(key) in self.strings else -2

    def pipeline(self):
        return FakePipeline(self)

    def keys(self, _pattern):
        self.keys_calls += 1
        raise AssertionError("KEYS must not be used")

    def _commit(self, commands):
        for command, args in commands:
            self.write_calls.append((command, args))
            self.committed_writes.append((command, args))
            if command == "zrem":
                _key, *job_ids = args
                for job_id in job_ids:
                    self.queue.pop(_as_bytes(job_id), None)
            elif command == "delete":
                for key in args:
                    self.strings.pop(_as_bytes(key), None)


class FakePipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def watch(self, *keys):
        self.watched_keys = tuple(_as_bytes(key) for key in keys)

    def unwatch(self):
        return None

    def multi(self):
        return None

    def execute(self):
        if self.redis_client.watch_error:
            raise WatchError("changed")
        self.redis_client._commit(self.commands)
        return [1] * len(self.commands)

    def zrem(self, key, *job_ids):
        self.commands.append(("zrem", (_as_bytes(key), *job_ids)))
        return self

    def delete(self, *keys):
        self.commands.append(("delete", tuple(_as_bytes(key) for key in keys)))
        return self

    def type(self, key):
        return self.redis_client.type(key)

    def zrange(self, key, start, end, *, withscores=False):
        return self.redis_client.zrange(key, start, end, withscores=withscores)

    def scan_iter(self, *, match, count):
        return self.redis_client.scan_iter(match=match, count=count)

    def get(self, key):
        return self.redis_client.get(key)

    def exists(self, key):
        return self.redis_client.exists(key)


def _as_bytes(value):
    if isinstance(value, bytes):
        return value
    return str(value).encode()


def test_default_plan_selects_only_marker_referenced_queued_jobs():
    redis_client = FakeRedis(
        queue={b"queued-blocker": 1000.0, b"unrelated": 2000.0},
        strings={
            b"task:running:task-1": b"queued-blocker",
            b"task:dedupe:key-1": b"queued-blocker",
            b"task:running:task-2": b"running-job",
            b"arq:in-progress:running-job": b"1",
        },
    )

    plan = build_cleanup_plan(
        redis_client, all_pending=False, include_in_progress=False,
    )

    assert plan.selected_job_ids == (b"queued-blocker",)
    assert plan.protected_job_ids == (b"running-job",)
    assert plan.marker_keys == (b"task:dedupe:key-1", b"task:running:task-1",)
    assert plan.queue_scores == ((b"queued-blocker", 1000.0),)


def test_all_pending_selects_unreferenced_queue_jobs():
    redis_client = FakeRedis(
        queue={b"referenced": 1000.0, b"unreferenced": 2000.0},
        strings={b"task:running:task-1": b"referenced"},
    )

    plan = build_cleanup_plan(
        redis_client, all_pending=True, include_in_progress=False,
    )

    assert plan.selected_job_ids == (b"referenced", b"unreferenced")
    assert plan.marker_keys == (b"task:running:task-1",)


def test_default_plan_never_selects_in_progress_job():
    redis_client = FakeRedis(
        queue={b"running-job": 1000.0},
        strings={
            b"task:running:task-1": b"running-job",
            b"arq:in-progress:running-job": b"1",
        },
    )

    plan = build_cleanup_plan(
        redis_client, all_pending=False, include_in_progress=False,
    )

    assert plan.selected_job_ids == ()
    assert plan.protected_job_ids == (b"running-job",)
    assert plan.marker_keys == ()


def test_include_in_progress_selects_only_related_jobs():
    redis_client = FakeRedis(
        strings={
            b"task:running:task-1": b"running-job",
            b"arq:in-progress:running-job": b"1",
            b"arq:in-progress:unrelated": b"1",
        }
    )

    plan = build_cleanup_plan(
        redis_client, all_pending=False, include_in_progress=True,
    )

    assert plan.selected_job_ids == (b"running-job",)
    assert plan.protected_job_ids == ()
    assert plan.marker_keys == (b"task:running:task-1",)


def test_plan_rejects_wrong_queue_type():
    redis_client = FakeRedis(type_overrides={b"arq:queue": b"list"})

    with pytest.raises(CleanupStateError, match="arq:queue"):
        build_cleanup_plan(
            redis_client, all_pending=False, include_in_progress=False,
        )


def test_plan_rejects_wrong_marker_type():
    marker_key = b"task:running:task-1"
    redis_client = FakeRedis(
        strings={marker_key: b"queued-job"},
        type_overrides={marker_key: b"hash"},
    )

    with pytest.raises(CleanupStateError, match="task:running:task-1"):
        build_cleanup_plan(
            redis_client, all_pending=False, include_in_progress=False,
        )


def test_plan_rejects_empty_marker_job_id():
    redis_client = FakeRedis(strings={b"task:dedupe:key-1": b""})

    with pytest.raises(CleanupStateError, match="empty job id"):
        build_cleanup_plan(
            redis_client, all_pending=False, include_in_progress=False,
        )


def test_plan_uses_scan_instead_of_keys():
    redis_client = FakeRedis()

    build_cleanup_plan(
        redis_client, all_pending=False, include_in_progress=False,
    )

    assert redis_client.keys_calls == 0
    assert redis_client.scan_patterns == [
        b"task:running:*",
        b"task:dedupe:*",
    ]


def _selected_plan_fixture(*, watch_error=False, with_unrelated_keys=False):
    strings = {
        b"task:running:task-1": b"queued-blocker",
        b"task:dedupe:key-1": b"queued-blocker",
        b"arq:job:queued-blocker": b"serialized-job",
        b"arq:retry:queued-blocker": b"1",
        b"arq:result:queued-blocker": b"keep-result",
    }
    queue = {b"queued-blocker": 1000.0}
    if with_unrelated_keys:
        queue[b"unrelated-job"] = 2000.0
        strings.update(
            {
                b"arq:job:unrelated-job": b"unrelated-payload",
                b"host_remote:callback:1": b"callback",
                b"credential:state:1": b"credential",
            }
        )
    redis_client = FakeRedis(
        queue=queue, strings=strings, watch_error=watch_error,
    )
    plan = build_cleanup_plan(
        redis_client, all_pending=False, include_in_progress=False,
    )
    return redis_client, plan


def test_backup_is_created_with_restricted_permissions(tmp_path):
    redis_client, plan = _selected_plan_fixture()

    backup_path = create_cleanup_backup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )

    assert stat.S_IMODE(backup_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    assert payload["redis_db"] == 1
    assert payload["queue_scores"] == {"queued-blocker": 1000.0}
    assert payload["marker_items"]["task:running:task-1"] == "queued-blocker"
    assert payload["keys"]["arq:job:queued-blocker"]["dump"]
    assert "password" not in json.dumps(payload).lower()


def test_backup_failure_performs_no_redis_writes(tmp_path, monkeypatch):
    redis_client, plan = _selected_plan_fixture()
    monkeypatch.setattr(os, "open", Mock(side_effect=OSError("read only")))

    with pytest.raises(CleanupBackupError):
        create_cleanup_backup(
            redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
        )

    assert redis_client.write_calls == []


def test_apply_rejects_queue_score_drift_without_deleting():
    redis_client, plan = _selected_plan_fixture()
    redis_client.queue[b"queued-blocker"] = 9999.0

    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)

    assert redis_client.write_calls == []


def test_apply_rejects_marker_value_drift_without_deleting():
    redis_client, plan = _selected_plan_fixture()
    redis_client.strings[b"task:running:task-1"] = b"replacement"

    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)

    assert redis_client.write_calls == []


def test_apply_rejects_job_key_type_drift_without_deleting():
    redis_client, plan = _selected_plan_fixture()
    redis_client.type_overrides[b"arq:job:queued-blocker"] = b"hash"

    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)

    assert redis_client.write_calls == []


def test_watch_error_is_reported_as_drift():
    redis_client, plan = _selected_plan_fixture(watch_error=True)

    with pytest.raises(CleanupDriftError):
        apply_cleanup_plan(redis_client, plan)

    assert redis_client.committed_writes == []


def test_apply_deletes_only_selected_job_keys_and_markers():
    redis_client, plan = _selected_plan_fixture(with_unrelated_keys=True)

    result = apply_cleanup_plan(redis_client, plan)

    assert result.deleted_job_count == 1
    assert result.deleted_marker_count == 2
    assert result.remaining_queue_jobs == 1
    assert b"queued-blocker" not in redis_client.queue
    assert b"arq:job:queued-blocker" not in redis_client.strings
    assert b"arq:retry:queued-blocker" not in redis_client.strings
    assert b"task:running:task-1" not in redis_client.strings
    assert b"task:dedupe:key-1" not in redis_client.strings
    assert b"unrelated-job" in redis_client.queue
    assert b"arq:result:queued-blocker" in redis_client.strings
    assert b"host_remote:callback:1" in redis_client.strings
    assert b"credential:state:1" in redis_client.strings
