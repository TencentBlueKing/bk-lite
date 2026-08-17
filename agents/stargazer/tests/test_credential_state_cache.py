import pytest

import core.infra.credential_state_cache as cache_module
from core.infra.credential_state_cache import CredentialStateCache


class Redis:
    def __init__(self):
        self.values = {}
        self.scores = {}
        self.get_calls = 0
        self.force_append_conflict = False

    async def get(self, key):
        self.get_calls += 1
        return self.values.get(key)

    async def set(self, key, value, **_kwargs):
        self.values[key] = value

    async def delete(self, key):
        self.values.pop(key, None)

    async def scan(self, **_kwargs):
        return 0, []

    async def zadd(self, key, values):
        self.values.setdefault(key, []).extend(values)

    async def zremrangebyscore(self, *_args):
        return 0

    async def zrangebyscore(self, key, **_kwargs):
        minimum = _kwargs.get("min", "-inf")
        maximum = _kwargs.get("max", "+inf")
        start = _kwargs.get("start", 0)
        count = _kwargs.get("num")
        withscores = _kwargs.get("withscores", False)
        minimum_exclusive = isinstance(minimum, str) and minimum.startswith("(")
        if minimum_exclusive:
            minimum = minimum[1:]
        minimum = float("-inf") if minimum == "-inf" else float(minimum)
        maximum = float("inf") if maximum == "+inf" else float(maximum)
        items = sorted(
            (
                (member, self.scores[(key, member)])
                for member in self.values.get(key, [])
                if (
                    (
                        self.scores[(key, member)] > minimum
                        if minimum_exclusive
                        else self.scores[(key, member)] >= minimum
                    )
                    and self.scores[(key, member)] <= maximum
                )
            ),
            key=lambda item: (item[1], item[0]),
        )
        items = items[start : start + count if count is not None else None]
        return items if withscores else [member for member, _score in items]

    async def eval(self, _script, _numkeys, *args):
        if _numkeys == 1:
            clock_key, requested_score = args
            return max(
                int(requested_score), int(self.values.get(clock_key, 0)) + 1
            )
        stream_key, dedupe_key, clock_key, score, payload, _retention, _cutoff = args
        if self.force_append_conflict:
            return -1
        if dedupe_key in self.values:
            return 0
        if int(score) <= int(self.values.get(clock_key, 0)):
            return -1
        self.values[clock_key] = int(score)
        self.values.setdefault(stream_key, []).append(payload)
        self.scores[(stream_key, payload)] = score
        self.values[dedupe_key] = "1"
        return 1


@pytest.mark.asyncio
async def test_cache_reuses_application_redis_client(monkeypatch):
    redis = Redis()
    calls = 0

    async def get_client():
        nonlocal calls
        calls += 1
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", get_client)
    redis.values[CredentialStateCache._success_key("task-1", "host-1")] = (
        "credential-1"
    )

    assert await CredentialStateCache.get_success_credential(
        "task-1", "host-1"
    ) == "credential-1"
    await CredentialStateCache.close_pool()

    assert calls == 1
    assert redis.get_calls == 1


@pytest.mark.asyncio
async def test_result_events_remain_on_ordinary_redis(monkeypatch):
    redis = Redis()

    async def get_client():
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", get_client)
    await CredentialStateCache.append_result_event(
        {
            "collect_task_id": "task-1",
            "host": "10.10.24.1",
            "finished_at": "2026-08-05T00:00:00+00:00",
        }
    )

    raw = redis.values[CredentialStateCache._event_stream_key()][0]
    assert CredentialStateCache._decode_event_member(raw)["collect_task_id"] == "task-1"


@pytest.mark.asyncio
async def test_result_event_with_stable_id_is_appended_once(monkeypatch):
    redis = Redis()

    async def get_client():
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", get_client)
    event = {
        "event_id": "stable-result-event-id",
        "collect_task_id": "task-1",
        "host": "10.10.24.1",
    }

    await CredentialStateCache.append_result_event(event)
    await CredentialStateCache.append_result_event(event)

    raw_events = redis.values[CredentialStateCache._event_stream_key()]
    assert len(raw_events) == 1
    assert (
        CredentialStateCache._decode_event_member(raw_events[0])["event_id"]
        == "stable-result-event-id"
    )


@pytest.mark.asyncio
async def test_result_events_use_unique_legacy_cursor_times_for_same_observation(monkeypatch):
    redis = Redis()

    async def get_client():
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", get_client)
    observed_at = "2026-08-14T00:00:00+00:00"
    for index in range(3):
        await CredentialStateCache.append_result_event(
            {
                "event_id": f"event-{index}",
                "collect_task_id": "task-1",
                "host": f"10.0.0.{index}",
                "finished_at": observed_at,
            }
        )

    events = await CredentialStateCache.list_result_events(limit=3)
    finished_at_values = [event["finished_at"] for event in events]
    assert len(set(finished_at_values)) == 3
    assert all(event["observed_at"] == observed_at for event in events)

    # 模拟回滚后的旧读取器：纯时间排他游标可逐页前进，不会卡在同毫秒。
    legacy_pages = []
    legacy_cursor = ""
    for _index in range(3):
        minimum = (
            f"({CredentialStateCache._event_score(legacy_cursor)}"
            if legacy_cursor
            else "-inf"
        )
        raw_page = await redis.zrangebyscore(
            CredentialStateCache._event_stream_key(),
            min=minimum,
            max="+inf",
            start=0,
            num=1,
        )
        page = [CredentialStateCache._decode_event_member(item) for item in raw_page]
        legacy_pages.extend(page)
        legacy_cursor = page[-1]["finished_at"]

    assert [event["event_id"] for event in legacy_pages] == [
        "event-0",
        "event-1",
        "event-2",
    ]


@pytest.mark.asyncio
async def test_result_event_append_fails_after_bounded_cas_conflicts(monkeypatch):
    redis = Redis()
    redis.force_append_conflict = True

    async def get_client():
        return redis

    monkeypatch.setattr(cache_module, "get_redis_client", get_client)
    with pytest.raises(RuntimeError, match="too busy"):
        await CredentialStateCache._append_result_event(
            {"event_id": "always-conflicts"}
        )
