"""即时告警内存匹配器测试。

关键不变量：InstantMatcher.match_in_memory 与 StrategyMatcher 的 Q 表达式语义完全一致。
"""

from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.aggregation.strategy.instant_matcher import InstantMatcher
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event


def _fake_event(**fields):
    """轻量伪事件，不入库，仅供内存匹配测试用。"""
    defaults = dict(
        title="测试事件",
        description="desc",
        level="1",
        service="api-gateway",
        location="北京机房",
        resource_type="service",
        resource_name="gateway-01",
        resource_id="gw-1",
        item="response_time",
        event_id="EVENT-X",
        event_type=1,
        push_source_id="lite-monitor",
        labels={},
        tags={},
    )
    defaults.update(fields)
    obj = SimpleNamespace(**defaults)
    obj.source = SimpleNamespace(name=fields.get("source_name", "src1"))
    return obj


# --------------------------------------------------------------------------
# 空 / 无效规则
# --------------------------------------------------------------------------

def test_empty_rules_returns_false():
    assert InstantMatcher.match_in_memory(_fake_event(), []) is False
    assert InstantMatcher.match_in_memory(_fake_event(), None) is False


def test_empty_inner_group_skipped():
    # 单空组 → 没有任何有效 OR 分支 → 不命中
    assert InstantMatcher.match_in_memory(_fake_event(), [[]]) is False


def test_invalid_operator_skipped():
    rules = [[{"key": "title", "operator": "nope", "value": "x"}]]
    assert InstantMatcher.match_in_memory(_fake_event(), rules) is False


def test_missing_key_or_operator():
    assert InstantMatcher.match_in_memory(_fake_event(), [[{"operator": "eq", "value": "x"}]]) is False
    assert InstantMatcher.match_in_memory(_fake_event(), [[{"key": "title", "value": "x"}]]) is False


# --------------------------------------------------------------------------
# 各操作符语义
# --------------------------------------------------------------------------

def test_eq_zh_and_en():
    e = _fake_event(title="abc")
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "eq", "value": "abc"}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "标题", "operator": "等于", "value": "abc"}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "eq", "value": "xyz"}]])


def test_ne():
    e = _fake_event(title="abc")
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "ne", "value": "xyz"}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "ne", "value": "abc"}]])


def test_icontains_and_not_contains():
    e = _fake_event(title="API Gateway Timeout")
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "contains", "value": "gateway"}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "包含", "value": "GATEWAY"}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "not_contains", "value": "gateway"}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "not_contains", "value": "absent"}]])


def test_regex():
    e = _fake_event(title="Order 123 failed")
    assert InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "regex", "value": r"\d+\s+failed"}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "regex", "value": r"^success"}]])
    # 非法正则不视为命中
    assert not InstantMatcher.match_in_memory(e, [[{"key": "title", "operator": "regex", "value": "("}]])


def test_in_and_not_in():
    e = _fake_event(level="1")
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "in", "value": ["0", "1"]}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "in", "value": ["2", "3"]}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "not_in", "value": ["2", "3"]}]])
    # 非列表参数 → 不命中
    assert not InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "in", "value": "1"}]])


def test_numeric_compare():
    e = _fake_event(level="2")
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "gt", "value": 1}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "gte", "value": 2}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "lt", "value": 3}]])
    assert InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "lte", "value": 2}]])
    assert not InstantMatcher.match_in_memory(e, [[{"key": "level", "operator": "gt", "value": 5}]])


# --------------------------------------------------------------------------
# AND / OR 嵌套
# --------------------------------------------------------------------------

def test_and_group_all_must_match():
    e = _fake_event(title="A", level="1")
    rules = [[
        {"key": "title", "operator": "eq", "value": "A"},
        {"key": "level", "operator": "eq", "value": "1"},
    ]]
    assert InstantMatcher.match_in_memory(e, rules)
    rules2 = [[
        {"key": "title", "operator": "eq", "value": "A"},
        {"key": "level", "operator": "eq", "value": "2"},
    ]]
    assert not InstantMatcher.match_in_memory(e, rules2)


def test_or_groups_any_can_match():
    e = _fake_event(title="A", level="1")
    rules = [
        [{"key": "title", "operator": "eq", "value": "B"}],          # 不命中
        [{"key": "level", "operator": "eq", "value": "1"}],          # 命中
    ]
    assert InstantMatcher.match_in_memory(e, rules)


# --------------------------------------------------------------------------
# 字段映射 + labels/tags 回退
# --------------------------------------------------------------------------

def test_field_map_alias():
    e = _fake_event(resource_name="host-1")
    # 中文别名 "对象实例" 应映射到 resource_name
    assert InstantMatcher.match_in_memory(e, [[{"key": "对象实例", "operator": "eq", "value": "host-1"}]])


def test_source_name_via_source_relation():
    e = _fake_event(source_name="src-prod")
    assert InstantMatcher.match_in_memory(e, [[{"key": "source", "operator": "contains", "value": "prod"}]])


def test_label_fallback():
    e = _fake_event(labels={"region": "us-east"})
    # region 不是 FIELD_MAP 已知字段，应回退到 labels
    assert InstantMatcher.match_in_memory(e, [[{"key": "region", "operator": "eq", "value": "us-east"}]])


def test_tag_fallback():
    e = _fake_event(tags={"env": "prod"})
    assert InstantMatcher.match_in_memory(e, [[{"key": "env", "operator": "eq", "value": "prod"}]])


# --------------------------------------------------------------------------
# 与 StrategyMatcher（DB 端）等价性对拍
# --------------------------------------------------------------------------

@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="src1", source_id="s-equiv", source_type="restful", secret="x")


@pytest.fixture
def db_event(db, source):
    return Event.objects.create(
        source=source,
        raw_data={},
        title="API Gateway Timeout",
        description="详情",
        level="1",
        service="api-gateway",
        location="北京机房",
        resource_type="service",
        resource_name="gateway-01",
        resource_id="gw-1",
        item="response_time",
        event_id="EVENT-EQUIV-1",
        push_source_id="lite-monitor",
        start_time=timezone.now(),
        labels={},
        tags={},
    )


@pytest.mark.django_db
def test_parity_with_strategy_matcher(db_event):
    """与 StrategyMatcher.match_events_to_strategy 在多组规则上的命中结果一致。"""
    test_cases = [
        [[{"key": "title", "operator": "contains", "value": "gateway"}]],
        [[{"key": "level", "operator": "in", "value": ["0", "1"]}]],
        [[{"key": "level", "operator": "gt", "value": 0}]],
        [
            [{"key": "title", "operator": "regex", "value": r"^API"}],
            [{"key": "service", "operator": "eq", "value": "missing"}],
        ],
        [[
            {"key": "title", "operator": "contains", "value": "gateway"},
            {"key": "level", "operator": "eq", "value": "1"},
        ]],
    ]
    from apps.alerts.models.models import Event as EventModel
    for rules in test_cases:
        in_mem = InstantMatcher.match_in_memory(db_event, rules)
        qs = StrategyMatcher.match_events_to_strategy(
            EventModel.objects.filter(pk=db_event.pk), rules
        )
        db_hit = qs.exists()
        assert in_mem == db_hit, f"parity broken for rules={rules}: mem={in_mem} db={db_hit}"
