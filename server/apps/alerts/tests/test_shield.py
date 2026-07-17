"""事件屏蔽覆盖测试。

对照 spec/prd/告警中心·配置：屏蔽策略在生效时间内匹配事件并置为屏蔽状态。
"""

import pytest
from django.utils import timezone

from apps.alerts.common.shield import EventShieldOperator, execute_shield_check_for_events
from apps.alerts.constants.constants import EventStatus
from apps.alerts.error import ShieldNotFoundError
from apps.alerts.models.alert_operator import AlertShield
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")


@pytest.fixture
def source2(db):
    """第二个源，用于验证 source_id 过滤不会误命中其他源。"""
    return AlertSource.objects.create(name="源2", source_id="s2", source_type="restful", secret="x")


def _make_event(source, event_id="E1", title="t", status=EventStatus.RECEIVED, **over):
    defaults = dict(
        source=source, raw_data={}, title=title, level="0",
        start_time=timezone.now(), event_id=event_id, status=status,
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


@pytest.mark.django_db
def test_shield_all_match_shields_events(source):
    _make_event(source, "E1")
    _make_event(source, "E2")
    AlertShield.objects.create(name="全屏蔽", match_type="all", match_rules=[], suppression_time={})

    result = execute_shield_check_for_events(["E1", "E2"])
    # 全部匹配 → 两条事件均被置为屏蔽状态
    assert Event.objects.filter(status=EventStatus.SHIELD).count() == 2
    assert result["shielded_events"] == 2
    assert result["unshielded_events"] == 0
    assert len(result["shield_results"]) == 2


@pytest.mark.django_db
def test_shield_filter_match_by_title(source):
    _make_event(source, "E1", title="CPU高")
    _make_event(source, "E2", title="内存正常")
    AlertShield.objects.create(
        name="标题屏蔽",
        match_type="filter",
        match_rules=[[{"key": "title", "operator": "contains", "value": "CPU"}]],
        suppression_time={},
    )

    execute_shield_check_for_events(["E1", "E2"])
    # 仅标题含 CPU 的事件被屏蔽
    assert Event.objects.get(event_id="E1").status == EventStatus.SHIELD
    assert Event.objects.get(event_id="E2").status == EventStatus.RECEIVED


@pytest.mark.django_db
def test_shield_filter_match_by_source_id(source, source2):
    """前端 matchRule.tsx 选「告警源（按 ID）」时下发 key=source_id, value=String(source.id)。

    EventShieldOperator.FIELD_MAPPING 当前把 source_id 映射到 source__source_id（业务 ID 字符串），
    但前端发的是主键数字字符串（如 "1"），导致匹配永远 0 命中 → 屏蔽失效。
    修复后应能按主键 ID 过滤，命中指定源、排除其他源。
    """
    _make_event(source, "E1")
    _make_event(source2, "E2")
    AlertShield.objects.create(
        name="按源屏蔽",
        match_type="filter",
        match_rules=[[{"key": "source_id", "operator": "eq", "value": str(source.id)}]],
        suppression_time={},
    )

    execute_shield_check_for_events(["E1", "E2"])
    # 仅 source.id 对应的事件被屏蔽
    assert Event.objects.get(event_id="E1").status == EventStatus.SHIELD, \
        f"源1 (id={source.id}) 的事件应被按 source_id 过滤命中并屏蔽"
    assert Event.objects.get(event_id="E2").status == EventStatus.RECEIVED, \
        "源2 的事件不应被源1 的屏蔽策略误命中"


@pytest.mark.django_db
def test_shield_filter_match_by_level(source):
    """前端按「级别」屏蔽下发的规则 key 为 level（value 为 level_id），应能匹配并屏蔽事件。"""
    _make_event(source, "E1", level="2")
    _make_event(source, "E2", level="1")
    AlertShield.objects.create(
        name="级别屏蔽",
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "eq", "value": "2"}]],
        suppression_time={},
    )

    execute_shield_check_for_events(["E1", "E2"])
    # 仅 level=2 的事件被屏蔽
    assert Event.objects.get(event_id="E1").status == EventStatus.SHIELD
    assert Event.objects.get(event_id="E2").status == EventStatus.RECEIVED


@pytest.mark.django_db
def test_shield_no_active_shields(source):
    _make_event(source, "E1")
    result = execute_shield_check_for_events(["E1"])
    assert result["shielded_events"] == 0
    assert result["unshielded_events"] == 1


@pytest.mark.django_db
def test_shield_empty_event_ids():
    result = execute_shield_check_for_events([])
    assert result["total_events"] == 0


@pytest.mark.django_db
def test_shield_time_range_not_matched(source):
    _make_event(source, "E1")
    # 一次性时间范围在过去 → 不生效
    AlertShield.objects.create(
        name="过期屏蔽",
        match_type="all",
        match_rules=[],
        suppression_time={"type": "one", "start_time": "2020-01-01 00:00:00", "end_time": "2020-01-02 00:00:00"},
    )
    result = execute_shield_check_for_events(["E1"])
    assert result["shielded_events"] == 0


@pytest.mark.django_db
def test_shield_operator_raises_when_no_shields(source):
    _make_event(source, "E1")
    with pytest.raises(ShieldNotFoundError):
        EventShieldOperator(["E1"])


@pytest.mark.django_db
def test_shield_check_with_preloaded_empty_shields(source):
    _make_event(source, "E1")
    # 传入空 queryset → 跳过
    result = execute_shield_check_for_events(["E1"], active_shields=AlertShield.objects.none())
    assert result["shielded_events"] == 0
    assert result["unshielded_events"] == 1


@pytest.mark.django_db
def test_shield_with_preloaded_shields(source):
    _make_event(source, "E1")
    shield_qs = AlertShield.objects.all()
    AlertShield.objects.create(name="全屏蔽", match_type="all", match_rules=[], suppression_time={})
    execute_shield_check_for_events(["E1"], active_shields=shield_qs)
    assert Event.objects.get(event_id="E1").status == EventStatus.SHIELD


@pytest.mark.django_db
def test_shield_day_time_range_matched(source):
    _make_event(source, "E1")
    # 全天时间范围 → 生效
    AlertShield.objects.create(
        name="全天屏蔽", match_type="all", match_rules=[],
        suppression_time={"type": "day", "start_time": "00:00:00", "end_time": "23:59:59"},
    )
    execute_shield_check_for_events(["E1"])
    assert Event.objects.get(event_id="E1").status == EventStatus.SHIELD


@pytest.mark.django_db
def test_shield_no_matching_events_returns_zero(source):
    # 事件已是 SHIELD 状态 → 不再匹配
    _make_event(source, "E1", status=EventStatus.SHIELD)
    AlertShield.objects.create(name="全屏蔽", match_type="all", match_rules=[], suppression_time={})
    result = execute_shield_check_for_events(["E1"])
    assert result["shielded_events"] == 0


@pytest.mark.django_db
def test_shield_event_not_found(source):
    AlertShield.objects.create(name="全屏蔽", match_type="all", match_rules=[], suppression_time={})
    # 事件 ID 不存在 → EventNotFoundError 被吞，返回零结果
    result = execute_shield_check_for_events(["NONEXISTENT"])
    assert result["shielded_events"] == 0
