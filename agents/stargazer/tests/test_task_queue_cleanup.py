import fnmatch

import pytest

from core.task_queue_cleanup import CleanupStateError, build_cleanup_plan


class FakeRedis:
    def __init__(self, *, queue=None, strings=None, type_overrides=None):
        self.queue = dict(queue or {})
        self.strings = dict(strings or {})
        self.type_overrides = dict(type_overrides or {})
        self.scan_patterns = []
        self.keys_calls = 0

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

    def keys(self, _pattern):
        self.keys_calls += 1
        raise AssertionError("KEYS must not be used")


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
        redis_client,
        all_pending=False,
        include_in_progress=False,
    )

    assert plan.selected_job_ids == (b"queued-blocker",)
    assert plan.protected_job_ids == (b"running-job",)
    assert plan.marker_keys == (
        b"task:dedupe:key-1",
        b"task:running:task-1",
    )
    assert plan.queue_scores == ((b"queued-blocker", 1000.0),)


def test_all_pending_selects_unreferenced_queue_jobs():
    redis_client = FakeRedis(
        queue={b"referenced": 1000.0, b"unreferenced": 2000.0},
        strings={b"task:running:task-1": b"referenced"},
    )

    plan = build_cleanup_plan(
        redis_client,
        all_pending=True,
        include_in_progress=False,
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
        redis_client,
        all_pending=False,
        include_in_progress=False,
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
        redis_client,
        all_pending=False,
        include_in_progress=True,
    )

    assert plan.selected_job_ids == (b"running-job",)
    assert plan.protected_job_ids == ()
    assert plan.marker_keys == (b"task:running:task-1",)


def test_plan_rejects_wrong_queue_type():
    redis_client = FakeRedis(type_overrides={b"arq:queue": b"list"})

    with pytest.raises(CleanupStateError, match="arq:queue"):
        build_cleanup_plan(
            redis_client,
            all_pending=False,
            include_in_progress=False,
        )


def test_plan_rejects_wrong_marker_type():
    marker_key = b"task:running:task-1"
    redis_client = FakeRedis(
        strings={marker_key: b"queued-job"},
        type_overrides={marker_key: b"hash"},
    )

    with pytest.raises(CleanupStateError, match="task:running:task-1"):
        build_cleanup_plan(
            redis_client,
            all_pending=False,
            include_in_progress=False,
        )


def test_plan_rejects_empty_marker_job_id():
    redis_client = FakeRedis(strings={b"task:dedupe:key-1": b""})

    with pytest.raises(CleanupStateError, match="empty job id"):
        build_cleanup_plan(
            redis_client,
            all_pending=False,
            include_in_progress=False,
        )


def test_plan_uses_scan_instead_of_keys():
    redis_client = FakeRedis()

    build_cleanup_plan(
        redis_client,
        all_pending=False,
        include_in_progress=False,
    )

    assert redis_client.keys_calls == 0
    assert redis_client.scan_patterns == [
        b"task:running:*",
        b"task:dedupe:*",
    ]
