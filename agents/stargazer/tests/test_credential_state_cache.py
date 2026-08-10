import json

import pytest

import core.infra.credential_state_cache as cache_module
from core.infra.credential_state_cache import CredentialStateCache


class Redis:
    def __init__(self):
        self.values = {}
        self.get_calls = 0

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
        return self.values.get(key, [])


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
    assert json.loads(raw)["collect_task_id"] == "task-1"
