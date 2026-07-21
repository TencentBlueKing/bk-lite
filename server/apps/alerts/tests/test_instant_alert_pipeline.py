"""即时告警端到端管线集成测试。

走完整 AlertSourceAdapter.main() 路径，验证:
- Event 入库
- Alert 入库 + M2M 关联
- 字段映射（level/title/team/group_by_field）
- 异步分派触发
- 与聚合管线互斥：AggregationProcessor 不再处理 INSTANT 策略
- 同一事件同时匹配 INSTANT 与 SMART_DENOISE → 互不影响
"""

from unittest import mock

import pytest

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.processor.instant_dispatcher import InstantStrategyCache
from apps.alerts.common.source_adapter.restful import RestFulAdapter
from apps.alerts.constants.constants import AlarmStrategyType, AlertStatus, LevelType
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level


@pytest.fixture
def levels(db):
    for lid in (0, 1, 2, 3):
        Level.objects.create(
            level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT,
        )
        Level.objects.create(
            level_id=lid, level_name=f"AL{lid}", level_display_name=f"告警{lid}", level_type=LevelType.ALERT,
        )


@pytest.fixture(autouse=True)
def _reset_cache():
    InstantStrategyCache.cache_clear()
    yield
    InstantStrategyCache.cache_clear()


@pytest.fixture
def source(db):
    return AlertSource.objects.create(
        name="src-restful",
        source_id="s-pipeline",
        source_type="restful",
        secret="x",
        config={
            "event_fields_mapping": {
                "title": "title",
                "description": "description",
                "level": "level",
                "item": "item",
                "resource_id": "resource_id",
                "resource_name": "resource_name",
                "resource_type": "resource_type",
                "service": "service",
                "location": "location",
                "external_id": "external_id",
                "start_time": "start_time",
                "value": "value",
                "action": "action",
            }
        },
    )


@pytest.fixture
def instant_strategy(db):
    return AlarmStrategy.objects.create(
        name="即时-X",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1, 2],
        match_rules=[[{"key": "title", "operator": "contains", "value": "失败"}]],
        params={"alert_template": {"title": "订单失败 [{service}]", "description": "{title} | {resource_name}"}},
    )


def _sample_payload(external_id="ext-1", title="订单失败"):
    return [{
        "title": title,
        "description": "订单 500 错误",
        "level": "1",
        "item": "order",
        "value": 1,
        "start_time": "2026-06-03T10:00:00+08:00",
        "action": "created",
        "external_id": external_id,
        "service": "order-service",
        "location": "上海机房",
        "labels": {
            "resource_id": "order-01",
            "resource_type": "service",
            "resource_name": "订单中心",
        },
    }]


@pytest.mark.django_db
def test_pipeline_creates_instant_alert(levels, source, instant_strategy):
    from apps.alerts.models import AlertOutbox

    adapter = RestFulAdapter(alert_source=source, secret="x", events=_sample_payload())
    adapter.main()

    assert Event.objects.count() == 1
    alerts = Alert.objects.all()
    assert alerts.count() == 1
    a = alerts.first()
    assert a.rule_id == str(instant_strategy.id)
    assert a.group_by_field == "instant"
    assert a.level == "1"  # 继承事件级别
    assert a.status == AlertStatus.UNASSIGNED
    assert a.team == [1, 2]
    records = {record.kind: record for record in AlertOutbox.objects.all()}
    assert records["auto_assignment"].payload == {"alert_ids": [a.alert_id]}
    assert records["action"].payload == {"alert_id": a.alert_id, "event_name": "created"}
    # 模板渲染
    assert "order-service" in a.title
    assert "订单中心" in a.content
    # M2M
    evt = Event.objects.first()
    assert list(a.events.values_list("id", flat=True)) == [evt.id]


@pytest.mark.django_db
def test_pipeline_no_alert_when_rule_misses(levels, source, instant_strategy):
    adapter = RestFulAdapter(
        alert_source=source, secret="x", events=_sample_payload(title="无匹配事件")
    )
    with mock.patch("apps.alerts.aggregation.processor.instant_dispatcher.current_app"):
        adapter.main()
    assert Event.objects.count() == 1
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_shielded_event_does_not_create_instant_alert(levels, source, instant_strategy):
    """事件级·不建警(2-1):命中屏蔽的事件不应生成即时告警。

    main() 中屏蔽先于即时旁路执行，dispatch 跳过 status=SHIELD 的事件。
    """
    from apps.alerts.models.alert_operator import AlertShield
    from apps.alerts.constants.constants import EventStatus

    AlertShield.objects.create(
        name="全屏蔽", match_type="all", match_rules=[], suppression_time={}, is_active=True,
    )
    adapter = RestFulAdapter(alert_source=source, secret="x", events=_sample_payload())
    with mock.patch(
        "apps.alerts.aggregation.processor.instant_dispatcher.current_app"
    ) as mock_app:
        adapter.main()
        # 被屏蔽 → 无新告警 → 不触发异步分派
        assert not mock_app.send_task.called

    assert Event.objects.count() == 1
    assert Event.objects.first().status == EventStatus.SHIELD
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_aggregation_processor_excludes_instant(instant_strategy):
    """AggregationProcessor 的 active strategies 列表绝不包含 INSTANT 策略。"""
    proc = AggregationProcessor()
    actives = proc._get_active_strategies()
    sids = [s.id for s in actives]
    assert instant_strategy.id not in sids


@pytest.mark.django_db
def test_aggregation_processor_still_returns_smart_denoise(db, instant_strategy):
    smart = AlarmStrategy.objects.create(
        name="降噪", strategy_type=AlarmStrategyType.SMART_DENOISE, is_active=True,
        team=[1], dispatch_team=[1], match_rules=[[]], params={"window_size": 10},
    )
    proc = AggregationProcessor()
    actives = proc._get_active_strategies()
    sids = [s.id for s in actives]
    assert smart.id in sids
    assert instant_strategy.id not in sids
