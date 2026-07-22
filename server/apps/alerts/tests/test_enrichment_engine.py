import pytest
from types import SimpleNamespace
from apps.alerts.enrichment.engine import EnrichmentEngine
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
        is_active=True, match_rules=[], provider_type="counting_test",
        input_binding={"model_id": "resource_type", "_id": "resource_id"},
        provider_config={}, output_projection=[{"source": "owner"}],
        on_multiple="first", resolved_namespace="cmdb",
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
