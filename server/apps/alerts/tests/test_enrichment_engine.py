import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from apps.alerts.enrichment.engine import EnrichmentEngine
from apps.alerts.enrichment.keys import build_binding_key
from apps.alerts.enrichment.providers.base import EnrichmentProvider, register_provider


@register_provider
class _CountingProvider(EnrichmentProvider):
    provider_type = "counting_test"
    calls = []

    def fetch_batch(self, keys, config):
        type(self).calls.append(list(keys))
        return {k: [{"owner": "alice", "biz": "pay"}] for k in keys}


def _rule(**over):
    base = dict(
        id=1,
        is_active=True,
        match_rules=[],
        provider_type="counting_test",
        input_binding={"model_id": "resource_type", "_id": "resource_id"},
        provider_config={},
        output_projection=[{"source": "owner"}],
        on_multiple="first",
        resolved_namespace="cmdb",
        team=[1],
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _clear():
    _CountingProvider.calls = []
    from django.core.cache import cache

    cache.clear()


def test_enrich_writes_namespaced_field():
    events = [{"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}]
    EnrichmentEngine(rules=[_rule()]).enrich_batch(events)
    assert events[0]["enrichment"]["cmdb"] == {"owner": "alice"}


def test_dedup_same_resource_single_provider_call():
    events = [
        {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]},
        {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]},
    ]
    EnrichmentEngine(rules=[_rule()]).enrich_batch(events)
    assert len(_CountingProvider.calls[0]) == 1


def test_unmatched_event_skipped():
    events = [{"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}]
    rule = _rule(match_rules=[[{"key": "resource_type", "operator": "eq", "value": "switch"}]])
    EnrichmentEngine(rules=[rule]).enrich_batch(events)
    assert events[0]["enrichment"] == {}


def test_missing_binding_field_skipped():
    events = [{"resource_type": "host", "enrichment": {}, "team": [1]}]  # 缺 resource_id
    EnrichmentEngine(rules=[_rule()]).enrich_batch(events)
    assert events[0]["enrichment"] == {}


def test_provider_exception_does_not_raise():
    class _Boom(EnrichmentProvider):
        provider_type = "boom_test"

        def fetch_batch(self, keys, config):
            raise RuntimeError("down")

    register_provider(_Boom)
    events = [{"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}]
    EnrichmentEngine(rules=[_rule(provider_type="boom_test")]).enrich_batch(events)
    assert events[0]["enrichment"] == {}
    assert "down" not in str(events[0]["enrichment_meta"])


# Fix 2: 不同 provider_config 不共享缓存
def test_different_provider_config_no_cache_collision():
    """相同 binding_key 但不同 provider_config 的规则不能命中彼此的缓存。"""
    events_a = [{"resource_type": "host", "resource_id": "99", "enrichment": {}, "team": [1]}]
    events_b = [{"resource_type": "host", "resource_id": "99", "enrichment": {}, "team": [1]}]

    rule_a = _rule(provider_config={"env": "prod"})
    rule_b = _rule(provider_config={"env": "test"})

    EnrichmentEngine(rules=[rule_a]).enrich_batch(events_a)
    _CountingProvider.calls.clear()  # 清空调用记录，只观察第二次
    EnrichmentEngine(rules=[rule_b]).enrich_batch(events_b)

    # rule_b 有不同的 provider_config，应当 cache miss → 再次调用 provider（calls 非空）
    assert len(_CountingProvider.calls) >= 1, "不同 provider_config 不应命中 rule_a 的缓存"


# Fix 3: 负缓存哨兵行为（使用 LocMemCache 绕过测试全局 DummyCache）
def test_negative_cache_sentinel_returns_empty(settings):
    """空结果写入缓存后，再次调用应直接返回空，且不再 hit provider。
    全局 conftest 使用 DummyCache，此测试临时切换为 LocMemCache 以验证缓存语义。
    """
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    # 重置 Django cache 连接
    from django.core.cache import cache as django_cache

    django_cache.close()

    class _EmptyProvider(EnrichmentProvider):
        provider_type = "empty_test"
        calls = 0

        def fetch_batch(self, keys, config):
            type(self).calls += 1
            return {}  # 始终返回空

    register_provider(_EmptyProvider)
    _EmptyProvider.calls = 0

    rule = _rule(provider_type="empty_test")
    events1 = [{"resource_type": "host", "resource_id": "42", "enrichment": {}, "team": [1]}]
    events2 = [{"resource_type": "host", "resource_id": "42", "enrichment": {}, "team": [1]}]

    EnrichmentEngine(rules=[rule]).enrich_batch(events1)
    assert _EmptyProvider.calls == 1  # 第一次走 provider

    EnrichmentEngine(rules=[rule]).enrich_batch(events2)
    assert _EmptyProvider.calls == 1  # 第二次应命中负缓存，不再调用 provider
    assert events2[0]["enrichment"] == {}  # 空结果


def test_rule_does_not_enrich_event_from_another_team():
    event = {
        "resource_type": "host",
        "resource_id": "cross-tenant",
        "enrichment": {},
        "team": [2],
    }

    EnrichmentEngine(rules=[_rule(team=[1])]).enrich_batch([event])

    assert event["enrichment"] == {}
    assert _CountingProvider.calls == []


def test_provider_failed_key_is_not_negative_cached(settings):
    from django.core.cache import cache

    from apps.alerts.enrichment.providers.base import FetchBatchResult

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.close()

    class _FlakyProvider(EnrichmentProvider):
        provider_type = "flaky_test"
        calls = 0

        def fetch_batch(self, keys, config):
            type(self).calls += 1
            if type(self).calls == 1:
                return FetchBatchResult(records={key: [] for key in keys}, failed_keys=set(keys))
            return {key: [{"owner": "alice"}] for key in keys}

    register_provider(_FlakyProvider)
    first = [{"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}]
    second = [{"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}]
    rule = _rule(provider_type="flaky_test")

    EnrichmentEngine(rules=[rule]).enrich_batch(first)
    binding_key = build_binding_key({"model_id": "host", "_id": "1"})
    provider_config = {"_authorized_team_ids": [1]}
    assert cache.get(EnrichmentEngine._cache_key("flaky_test", provider_config, binding_key)) is None
    cache.delete(EnrichmentEngine._circuit_key("flaky_test", provider_config))
    EnrichmentEngine(rules=[rule]).enrich_batch(second)

    assert _FlakyProvider.calls == 2
    assert second[0]["enrichment"]["cmdb"] == {"owner": "alice"}


def test_provider_circuit_breaker_skips_repeated_failure(settings):
    from django.core.cache import cache

    from apps.alerts.enrichment.providers.base import FetchBatchResult

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.close()

    class _DownProvider(EnrichmentProvider):
        provider_type = "down_test"
        calls = 0

        def fetch_batch(self, keys, config):
            type(self).calls += 1
            return FetchBatchResult(records={}, failed_keys=set(keys))

    register_provider(_DownProvider)
    rule = _rule(provider_type="down_test")
    events = [
        {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]},
        {"resource_type": "host", "resource_id": "2", "enrichment": {}, "team": [1]},
        {"resource_type": "host", "resource_id": "3", "enrichment": {}, "team": [1]},
    ]

    EnrichmentEngine(rules=[rule]).enrich_batch([events[0]])
    EnrichmentEngine(rules=[rule]).enrich_batch([events[1]])
    EnrichmentEngine(rules=[rule]).enrich_batch([events[2]])

    assert _DownProvider.calls == 2


def test_runtime_namespace_collision_preserves_both_results():
    class _OwnerProvider(EnrichmentProvider):
        provider_type = "owner_test"

        def fetch_batch(self, keys, config):
            return {key: [{"owner": config["owner"]}] for key in keys}

    register_provider(_OwnerProvider)
    event = {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}
    alice = _rule(id=1, provider_type="owner_test", provider_config={"owner": "alice"})
    bob = _rule(id=2, provider_type="owner_test", provider_config={"owner": "bob"})

    EnrichmentEngine(rules=[alice, bob]).enrich_batch([event])

    assert event["enrichment"]["cmdb"] == {
        "owner": "alice",
        "_meta": {
            "schema_version": 1,
            "status": "conflict",
            "rule_ids": [1, 2],
            "conflicts": {"owner": ["bob"]},
        },
    }


def test_enrich_batch_returns_bounded_summary():
    events = [
        {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]},
        {"resource_type": "host", "resource_id": "2", "enrichment": {}, "team": [1]},
    ]

    result = EnrichmentEngine(rules=[_rule()]).enrich_batch(events)

    assert result.events is events
    assert result.summary.received == 2
    assert result.summary.enriched == 2
    assert result.summary.failed == 0


def test_more_than_500_unique_keys_are_chunked_without_loss():
    events = [{"resource_type": "host", "resource_id": str(index), "enrichment": {}, "team": [1]} for index in range(1201)]

    result = EnrichmentEngine(rules=[_rule()]).enrich_batch(events)

    assert [len(call) for call in _CountingProvider.calls] == [500, 500, 201]
    assert result.summary.enriched == 1201
    assert all(event["enrichment"]["cmdb"]["owner"] == "alice" for event in events)


def test_singleflight_coalesces_concurrent_cold_lookup(settings):
    from django.core.cache import cache

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.close()
    started = Event()
    release = Event()

    class _SlowProvider(EnrichmentProvider):
        provider_type = "slow_singleflight_test"
        calls = 0

        def fetch_batch(self, keys, config):
            type(self).calls += 1
            started.set()
            assert release.wait(timeout=1)
            return {key: [{"owner": "alice"}] for key in keys}

    register_provider(_SlowProvider)
    rule = _rule(provider_type="slow_singleflight_test")
    first = [{"resource_type": "host", "resource_id": "same", "enrichment": {}, "team": [1]}]
    second = [{"resource_type": "host", "resource_id": "same", "enrichment": {}, "team": [1]}]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(EnrichmentEngine(rules=[rule]).enrich_batch, first)
        assert started.wait(timeout=1)
        second_future = pool.submit(EnrichmentEngine(rules=[rule]).enrich_batch, second)
        time.sleep(0.03)
        release.set()
        first_result = first_future.result(timeout=1)
        second_result = second_future.result(timeout=1)

    assert _SlowProvider.calls == 1
    assert first_result.summary.enriched == 1
    assert second_result.summary.inflight_coalesced == 1
    assert second[0]["enrichment"]["cmdb"]["owner"] == "alice"


def test_batch_deadline_stops_unstarted_chunks_without_negative_cache():
    class _Clock:
        now = 0.0

        def __call__(self):
            return self.now

    clock = _Clock()

    class _DeadlineProvider(EnrichmentProvider):
        provider_type = "deadline_test"
        calls = []

        def fetch_batch(self, keys, config):
            type(self).calls.append(list(keys))
            clock.now = 2.0
            return {key: [{"owner": "alice"}] for key in keys}

    register_provider(_DeadlineProvider)
    events = [{"resource_type": "host", "resource_id": str(index), "enrichment": {}, "team": [1]} for index in range(600)]

    result = EnrichmentEngine(rules=[_rule(provider_type="deadline_test")], clock=clock, batch_budget_seconds=1).enrich_batch(events)

    assert [len(call) for call in _DeadlineProvider.calls] == [500]
    assert result.summary.enriched == 500
    assert result.summary.budget_exhausted == 100
    assert all(event["enrichment_meta"]["status"] == "failed" for event in events[500:])


def test_provider_slot_saturation_is_bounded_and_does_not_call_provider(monkeypatch):
    class _NoSlot:
        def acquire(self, timeout):
            return False

        def release(self):
            raise AssertionError("未取得槽位时不应释放")

    monkeypatch.setattr("apps.alerts.enrichment.engine._PROVIDER_SLOTS", _NoSlot())
    event = {"resource_type": "host", "resource_id": "1", "enrichment": {}, "team": [1]}

    result = EnrichmentEngine(rules=[_rule()]).enrich_batch([event])

    assert _CountingProvider.calls == []
    assert result.summary.provider_saturated == 1
    assert event["enrichment_meta"]["status"] == "failed"


def test_runtime_telemetry_matches_batch_summary(settings):
    from django.core.cache import cache

    from apps.alerts.enrichment.telemetry import read_runtime_metrics

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.close()
    cache.clear()
    event = {"resource_type": "host", "resource_id": "metrics", "enrichment": {}, "team": [1]}

    result = EnrichmentEngine(rules=[_rule()]).enrich_batch([event])
    runtime = read_runtime_metrics(cache)

    assert runtime["batch_total"] == 1
    assert runtime["summary"]["received"] == result.summary.received
    assert runtime["summary"]["enriched"] == result.summary.enriched


def test_telemetry_failure_does_not_interrupt_enrichment():
    class _BrokenTelemetry:
        def record_cache(self, *args):
            raise RuntimeError("telemetry unavailable")

        def record_provider(self, *args):
            raise RuntimeError("telemetry unavailable")

        def record(self, *args):
            raise RuntimeError("telemetry unavailable")

    event = {"resource_type": "host", "resource_id": "telemetry", "enrichment": {}, "team": [1]}

    result = EnrichmentEngine(rules=[_rule()], telemetry=_BrokenTelemetry()).enrich_batch([event])

    assert result.summary.enriched == 1
    assert event["enrichment"]["cmdb"]["owner"] == "alice"
