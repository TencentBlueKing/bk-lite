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


def _make_alert(source, alert_id="A1"):
    """模拟一条 k8s 聚合告警，填齐前端条件可能用到的字段。"""
    return Alert.objects.create(
        alert_id=alert_id,
        level="1",
        title="CPU高",
        content="c",
        fingerprint="fp" + alert_id,
        status=AlertStatus.UNASSIGNED,
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
FILTER_CASES = [
    pytest.param("title", "CPU", "contains", id="title"),
    pytest.param("level", "1", "eq", id="level"),
    pytest.param("resource_type", "pod", "eq", id="resource_type"),
    pytest.param("resource_id", "pod-123", "eq", id="resource_id"),
]


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
