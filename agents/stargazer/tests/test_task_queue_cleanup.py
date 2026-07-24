import base64
import fnmatch
import json
import os
import stat
from unittest.mock import Mock

import pytest
from core import task_queue_cleanup as cleanup
from core.task_queue_cleanup import (
    CleanupBackupError,
    CleanupDriftError,
    CleanupRestoreError,
    CleanupStateError,
    _payload_digest,
    apply_cleanup_plan,
    backup_and_apply_cleanup,
    build_cleanup_plan,
    create_cleanup_backup,
    restore_cleanup_backup,
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
        direct_zcard_error=False,
    ):
        self.queue = dict(queue or {})
        self.strings = dict(strings or {})
        self.type_overrides = dict(type_overrides or {})
        self.watch_error = watch_error
        self.direct_zcard_error = direct_zcard_error
        self.scan_patterns = []
        self.keys_calls = 0
        self.write_calls = []
        self.committed_writes = []
        self.events = []
        self.ttls = {key: 60_000 for key in self.strings}

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
        if self.direct_zcard_error:
            raise ConnectionError("standalone zcard failed")
        return len(self.queue)

    def dump(self, key):
        self.events.append("dump")
        key = _as_bytes(key)
        if key in self.strings:
            return b"redis-dump:" + self.strings[key]
        return None

    def pttl(self, key):
        return self.ttls.get(_as_bytes(key), -2)

    def restore(self, key, ttl, dumped, *, replace=False):
        key = _as_bytes(key)
        if key in self.strings and not replace:
            raise RuntimeError("target exists")
        normalized_dump = _as_bytes(dumped)
        if not normalized_dump.startswith(b"redis-dump:"):
            raise RuntimeError("invalid dump")
        self.strings[key] = normalized_dump.removeprefix(b"redis-dump:")
        self.ttls[key] = -1 if ttl == 0 else ttl

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            normalized_key = _as_bytes(key)
            deleted += int(normalized_key in self.strings)
            self.strings.pop(normalized_key, None)
            self.ttls.pop(normalized_key, None)
        return deleted

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
                    self.ttls.pop(_as_bytes(key), None)
            elif command == "restore":
                key, ttl, dumped = args
                self.strings[_as_bytes(key)] = dumped.removeprefix(
                    b"redis-dump:"
                )
                self.ttls[_as_bytes(key)] = -1 if ttl == 0 else ttl
            elif command == "zadd":
                _key, mapping = args
                self.queue.update(mapping)
            elif command == "renamenx":
                source, destination = args
                self.strings[destination] = self.strings.pop(source)
                self.ttls[destination] = self.ttls.pop(source)


class FakePipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def watch(self, *keys):
        self.redis_client.events.append("watch")
        self.watched_keys = tuple(_as_bytes(key) for key in keys)

    def unwatch(self):
        return None

    def multi(self):
        return None

    def execute(self):
        if self.redis_client.watch_error:
            raise WatchError("changed")
        self.redis_client._commit(self.commands)
        return [
            len(self.redis_client.queue) if command == "zcard" else 1
            for command, _args in self.commands
        ]

    def zrem(self, key, *job_ids):
        self.commands.append(("zrem", (_as_bytes(key), *job_ids)))
        return self

    def delete(self, *keys):
        self.commands.append(("delete", tuple(_as_bytes(key) for key in keys)))
        return self

    def restore(self, key, ttl, dumped, *, replace=False):
        assert replace is False
        self.commands.append(
            ("restore", (_as_bytes(key), ttl, _as_bytes(dumped)))
        )
        return self

    def zadd(self, key, mapping):
        self.commands.append(("zadd", (_as_bytes(key), mapping)))
        return self

    def renamenx(self, source, destination):
        self.commands.append(
            ("renamenx", (_as_bytes(source), _as_bytes(destination)))
        )
        return self

    def zcard(self, key):
        self.commands.append(("zcard", (_as_bytes(key),)))
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

    def zscore(self, key, value):
        return self.redis_client.zscore(key, value)

    def dump(self, key):
        return self.redis_client.dump(key)

    def pttl(self, key):
        return self.redis_client.pttl(key)


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


def test_apply_reads_remaining_count_inside_the_cleanup_transaction():
    redis_client, plan = _selected_plan_fixture()
    redis_client.direct_zcard_error = True

    result = apply_cleanup_plan(redis_client, plan)

    assert result.remaining_queue_jobs == 0
    assert redis_client.committed_writes[-1][0] == "zcard"


def test_backup_reads_are_protected_by_the_cleanup_watch(tmp_path):
    redis_client, plan = _selected_plan_fixture()

    backup_path, result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )

    assert backup_path.is_file()
    assert result.deleted_job_count == 1
    assert redis_client.events.index("watch") < redis_client.events.index(
        "dump"
    )


def test_backup_can_restore_values_ttls_and_queue_scores(tmp_path):
    redis_client, plan = _selected_plan_fixture()
    original_strings = dict(redis_client.strings)
    original_ttls = dict(redis_client.ttls)

    backup_path, _result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )
    restore_result = restore_cleanup_backup(
        redis_client, backup_path=backup_path, redis_db=1,
    )

    for key in plan.target_keys:
        if key in original_strings:
            assert redis_client.strings[key] == original_strings[key]
            assert redis_client.ttls[key] == original_ttls[key]
    assert redis_client.queue[b"queued-blocker"] == 1000.0
    expected_restored_keys = set(plan.target_keys) & set(original_strings)
    assert restore_result.restored_key_count == len(expected_restored_keys)
    assert restore_result.restored_queue_job_count == 1


def test_restore_never_overwrites_existing_queue_state(tmp_path):
    redis_client, plan = _selected_plan_fixture()
    backup_path, _result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )
    restore_cleanup_backup(redis_client, backup_path=backup_path, redis_db=1)
    committed_write_count = len(redis_client.committed_writes)

    with pytest.raises(CleanupRestoreError, match="already exists"):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=1
        )

    assert len(redis_client.committed_writes) == committed_write_count


def test_restore_rejects_wrong_database_and_unexpected_keys(tmp_path):
    redis_client, plan = _selected_plan_fixture()
    backup_path = create_cleanup_backup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )

    with pytest.raises(CleanupRestoreError, match="invalid task queue backup"):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=2
        )

    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    payload["keys"]["credential:state:1"] = next(
        iter(payload["keys"].values())
    )
    payload["marker_items"]["credential:state:1"] = "queued-blocker"
    backup_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CleanupRestoreError, match="invalid task queue backup"):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=1
        )


def test_restore_rejects_payload_that_expands_its_own_job_allowlist(tmp_path):
    redis_client, plan = _selected_plan_fixture()
    backup_path, _result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    payload["selected_job_ids"].append("injected-job")
    payload["keys"]["arq:job:injected-job"] = next(
        iter(payload["keys"].values())
    )
    backup_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CleanupRestoreError, match="invalid task queue backup"):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=1
        )

    assert b"arq:job:injected-job" not in redis_client.strings


def test_damaged_dump_does_not_partially_restore_target_keys(tmp_path):
    redis_client, plan = _selected_plan_fixture()
    backup_path, _result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    marker_key = "task:running:task-1"
    payload["keys"][marker_key]["dump"] = base64.b64encode(
        b"invalid-dump"
    ).decode()
    payload["content_sha256"] = _payload_digest(payload)
    backup_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CleanupRestoreError):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=1
        )

    assert not any(key in redis_client.strings for key in plan.target_keys)
    assert not any(
        key.startswith(b"stargazer:task-queue-restore:tmp:")
        for key in redis_client.strings
    )


def test_restore_temp_key_collision_never_deletes_existing_data(
    tmp_path, monkeypatch,
):
    redis_client, plan = _selected_plan_fixture()
    backup_path, _result = backup_and_apply_cleanup(
        redis_client, plan, backup_dir=tmp_path / "backups", redis_db=1,
    )
    monkeypatch.setattr(cleanup.secrets, "token_hex", lambda _size: "fixed")
    collision_key = b"stargazer:task-queue-restore:tmp:fixed:0"
    redis_client.strings[collision_key] = b"existing-data"
    redis_client.ttls[collision_key] = -1

    with pytest.raises(CleanupRestoreError):
        restore_cleanup_backup(
            redis_client, backup_path=backup_path, redis_db=1
        )

    assert redis_client.strings[collision_key] == b"existing-data"
