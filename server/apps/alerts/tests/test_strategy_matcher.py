"""聚合策略事件匹配器覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：相关性规则通过 match_rules(外层OR/内层AND) 过滤事件。
"""

import pytest
from django.db.models import Q
from django.utils import timezone

from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


def _make_event(source, event_id, title="t", level="0", description="", **over):
    defaults = dict(
        source=source, raw_data={}, title=title, level=level, description=description,
        start_time=timezone.now(), event_id=event_id,
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


# --------------------------------------------------------------------------
# _build_condition_q
# --------------------------------------------------------------------------


def test_build_condition_q_missing_key():
    assert StrategyMatcher._build_condition_q({"operator": "eq", "value": "x"}) is None


def test_build_condition_q_none_value_non_ne():
    assert StrategyMatcher._build_condition_q({"key": "title", "operator": "eq", "value": None}) is None


def test_build_condition_q_unknown_operator():
    assert StrategyMatcher._build_condition_q({"key": "title", "operator": "weird", "value": "x"}) is None


def test_build_condition_q_eq():
    q = StrategyMatcher._build_condition_q({"key": "title", "operator": "eq", "value": "x"})
    assert isinstance(q, Q)


def test_build_condition_q_not_contains_empty_invalid():
    assert StrategyMatcher._build_condition_q({"key": "title", "operator": "not_contains", "value": ""}) is None


def test_build_condition_q_in_requires_list():
    assert StrategyMatcher._build_condition_q({"key": "level", "operator": "in", "value": "notalist"}) is None
    assert StrategyMatcher._build_condition_q({"key": "level", "operator": "in", "value": ["0", "1"]}) is not None


def test_build_condition_q_invalid_regex():
    assert StrategyMatcher._build_condition_q({"key": "title", "operator": "re", "value": "["}) is None


def test_build_condition_q_chinese_aliases():
    q = StrategyMatcher._build_condition_q({"key": "标题", "operator": "包含", "value": "x"})
    assert isinstance(q, Q)


# --------------------------------------------------------------------------
# match_events_to_strategy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_match_no_rules_returns_all(source):
    _make_event(source, "E1")
    _make_event(source, "E2")
    result = StrategyMatcher.match_events_to_strategy(Event.objects.all(), [])
    assert result.count() == 2


@pytest.mark.django_db
def test_match_and_group(source):
    _make_event(source, "E1", title="CPU", level="0")
    _make_event(source, "E2", title="CPU", level="1")
    rules = [[{"key": "title", "operator": "eq", "value": "CPU"}, {"key": "level", "operator": "eq", "value": "0"}]]
    result = StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules)
    assert {e.event_id for e in result} == {"E1"}


@pytest.mark.django_db
def test_match_or_groups(source):
    _make_event(source, "E1", title="CPU")
    _make_event(source, "E2", title="MEM")
    _make_event(source, "E3", title="DISK")
    rules = [
        [{"key": "title", "operator": "eq", "value": "CPU"}],
        [{"key": "title", "operator": "eq", "value": "MEM"}],
    ]
    result = StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules)
    assert {e.event_id for e in result} == {"E1", "E2"}


@pytest.mark.django_db
def test_match_all_invalid_returns_none(source):
    _make_event(source, "E1")
    rules = [[{"key": "title", "operator": "weird", "value": "x"}]]
    result = StrategyMatcher.match_events_to_strategy(Event.objects.all(), rules)
    assert result.count() == 0


@pytest.mark.django_db
def test_event_to_dict_merges_labels_tags(source):
    event = _make_event(source, "E1", labels={"region": "us"}, tags={"env": "prod"})
    d = StrategyMatcher._event_to_dict(event)
    assert d["event_id"] == "E1"
    assert d["region"] == "us"
    assert d["env"] == "prod"
