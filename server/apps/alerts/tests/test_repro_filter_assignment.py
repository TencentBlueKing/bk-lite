"""复现：按条件分派规则匹配不到聚合告警，导致告警生成但未分派。

覆盖前端 matchRule 组件可下发的全部条件 key（见 web ruleList / initialConditionLists，
分派弹窗 operateModal.tsx:302 用默认 ruleList）：source_id / level / resource_type /
resource_id，外加对照 title。逐一验证哪些 key 能正确匹配并分派。
"""

import pytest

from apps.alerts.common.assignment import AlertAssignmentOperator
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User

    return User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])


@pytest.fixture
def source(db):
    return AlertSource.objects.create(name="K8s集群", source_id="k8s", source_type="restful", secret="x")


@pytest.fixture
def source2(db):
    """第二个源，用于验证 source_id 过滤不会误命中其他源。"""
    return AlertSource.objects.create(name="Zabbix", source_id="zabbix", source_type="restful", secret="x")


def _make_alert(source, alert_id="A1"):
    """模拟一条 k8s 聚合告警，填齐前端条件可能用到的字段。"""
    return Alert.objects.create(
        alert_id=alert_id,
        level="1",
        title="CPU高",
        content="c",
        fingerprint="fp" + alert_id,
        status=AlertStatus.UNASSIGNED,
        source_id=source.id,              # FK 字段（2026-07-17 修复后必填）
        source_name=source.name,
        team=[1],
        resource_type="pod",
        resource_id="pod-123",
        resource_name="host1",
    )


def _make_assignment(match_rules):
    return AlertAssignment.objects.create(
        name="按条件分派",
        match_type="filter",
        is_active=True,
        personnel=["op1"],
        match_rules=match_rules,
        config={},
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
    )


# 前端 matchRule 可下发的条件 (key, value)；value 取自 _make_alert 中该告警的真实字段值
# level 值为 level_id（前端按 level_display_name 选、存 level_id）
# source_id 值是 AlertSource.id（数据库主键，前端 matchRule.tsx 选「告警源（按 ID）」时发 String(source.id)）
FILTER_CASES = [
    pytest.param("title", "CPU", "contains", id="title"),
    pytest.param("level", "1", "eq", id="level"),
    pytest.param("resource_type", "pod", "eq", id="resource_type"),
    pytest.param("resource_id", "pod-123", "eq", id="resource_id"),
]


@pytest.fixture
def source_id_value(source):
    """取 source 对象的数据库主键 id，跟前端 matchRule.tsx 行为一致（String(source.id)）。"""
    return str(source.id)


@pytest.mark.django_db
def test_filter_by_source_id_assigns_k8s_only(sys_user, source, source2, source_id_value):
    """按告警源 ID 过滤：K8s 源告警应被命中并分派，Zabbix 源告警不应被误命中。

    复现 2026-07-17 线上 bug:用户配 key=source_id, value=3 的分派策略,
    但 AlertAssignmentOperator.FIELD_MAPPING 把 source_id 映射到 source_name 字段,
    实际查询 source_name="3" 永远 0 命中, 告警产生但没处理人。
    """
    alert_k8s = _make_alert(source, "A1")
    alert_zbx = _make_alert(source2, "A2")
    # 把 A2 的 source 切到 Zabbix（_make_alert 用 source 参数填充）
    alert_zbx.refresh_from_db()

    _make_assignment([[{"key": "source_id", "operator": "eq", "value": source_id_value}]])

    AlertAssignmentOperator(["A1", "A2"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING, \
        "K8s 源告警应被按 source_id=3 的分派策略命中并分派"
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED, \
        "Zabbix 源告警不应被 K8s 源的分派策略误命中"


@pytest.mark.django_db
def test_filter_by_source_id_ne_excludes_target_source(sys_user, source, source2, source_id_value):
    """反向用例：ne 操作符应排除指定源。"""
    _make_alert(source, "A1")
    _make_alert(source2, "A2")

    _make_assignment([[{"key": "source_id", "operator": "ne", "value": source_id_value}]])

    AlertAssignmentOperator(["A1", "A2"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.UNASSIGNED, \
        "K8s 源告警应被 ne 排除"
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.PENDING, \
        "非 K8s 源告警应被 ne 保留"


@pytest.mark.django_db
@pytest.mark.parametrize("key,value,operator", FILTER_CASES)
def test_filter_condition_assigns(sys_user, source, key, value, operator):
    """每种条件都应能匹配到这条真实匹配的告警并完成分派。"""
    _make_alert(source, "A1")
    _make_assignment([[{"key": key, "operator": operator, "value": value}]])

    AlertAssignmentOperator(["A1"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING, f"条件 key={key} value={value} 应匹配并分派，实际仍为未分派"


@pytest.mark.django_db
def test_end_to_end_aggregation_level_assignment(sys_user, source):
    """端到端复现用户场景：k8s 事件 -> 聚合为告警 -> 按级别分派。

    聚合产生的真实告警 level 即 level_id；按级别分派应匹配并分派。
    """
    from django.utils import timezone

    from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
    from apps.alerts.constants.constants import EventAction, LevelType
    from apps.alerts.models.alert_operator import AlarmStrategy
    from apps.alerts.models.models import Event, Level

    for lid in (0, 1, 2):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.ALERT)

    # 分派策略：按级别(level=1) 过滤
    _make_assignment([[{"key": "level", "operator": "eq", "value": "1"}]])

    now = timezone.now()
    for i in range(3):
        Event.objects.create(
            source=source,
            raw_data={},
            title="CPU高",
            level="1",
            start_time=now,
            event_id=f"E{i}",
            action=EventAction.CREATED,
            service="svc-a",
            resource_name="host1",
            item="cpu",
            external_id=f"ext{i}",
        )
    AlarmStrategy.objects.create(
        name="降噪",
        strategy_type="smart_denoise",
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "title", "operator": "eq", "value": "CPU高"}]],
        params={"window_size": 60, "group_by": ["service"]},
    )

    AggregationProcessor().process_aggregation()

    from apps.alerts.models import AlertOutbox
    from apps.alerts.service.outbox import deliver_outbox_record

    assignment_record = AlertOutbox.objects.get(kind="auto_assignment")
    deliver_outbox_record(assignment_record.pk)

    alert = Alert.objects.first()
    assert alert is not None
    assert alert.level == "1", f"聚合告警 level 应为 level_id '1'，实际 {alert.level}"
    assert alert.status == AlertStatus.PENDING, f"k8s 聚合告警按级别分派应被分派，实际状态={alert.status}"
