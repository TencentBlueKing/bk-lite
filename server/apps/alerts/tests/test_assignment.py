"""告警自动分派覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：分派策略在生效时间内匹配未分派告警并分派给指定人员。
"""

import pytest

from apps.alerts.common.assignment import AlertAssignmentOperator, execute_auto_assignment_for_alerts
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.error import AlertNotFoundError
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Alert


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User

    return User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])


def _make_alert(alert_id="A1", status=AlertStatus.UNASSIGNED, **over):
    defaults = dict(
        alert_id=alert_id, level="0", title="CPU高", content="c", fingerprint="fp" + alert_id,
        status=status, source_name="prometheus", team=[1],
    )
    defaults.update(over)
    return Alert.objects.create(**defaults)


def _make_assignment(name="分派", match_type="all", **over):
    defaults = dict(
        name=name, match_type=match_type, is_active=True, personnel=["op1"],
        match_rules=[], config={}, notify_channels=[], notification_scenario=[],
        notification_frequency={},
    )
    defaults.update(over)
    return AlertAssignment.objects.create(**defaults)


@pytest.mark.django_db
def test_assignment_operator_no_alerts_raises():
    with pytest.raises(AlertNotFoundError):
        AlertAssignmentOperator(["nonexistent"])


@pytest.mark.django_db
def test_execute_auto_assignment_empty():
    result = execute_auto_assignment_for_alerts([])
    assert result["total_alerts"] == 0


@pytest.mark.django_db
def test_auto_assignment_all_match(sys_user):
    _make_alert("A1", status=AlertStatus.UNASSIGNED)
    _make_assignment(match_type="all")
    operator = AlertAssignmentOperator(["A1"])
    result = operator.execute_auto_assignment()
    assert result["total_alerts"] == 1
    # 全部匹配 → 分派成功，告警状态变为待响应
    alert = Alert.objects.get(alert_id="A1")
    assert alert.status == AlertStatus.PENDING


@pytest.mark.django_db
def test_auto_assignment_filter_match(sys_user):
    _make_alert("A1", title="CPU高")
    _make_alert("A2", title="内存正常", fingerprint="fp2")
    _make_assignment(
        match_type="filter",
        match_rules=[[{"key": "title", "operator": "contains", "value": "CPU"}]],
    )
    operator = AlertAssignmentOperator(["A1", "A2"])
    result = operator.execute_auto_assignment()
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_level_eq_list_matches_any_selected_level(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "eq", "value": ["0", "1"]}]],
    )

    AlertAssignmentOperator(["A1", "A2", "A3"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A3").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_level_ne_list_excludes_all_selected_levels(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "ne", "value": ["0", "1"]}]],
    )

    AlertAssignmentOperator(["A1", "A2", "A3"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.UNASSIGNED
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED
    assert Alert.objects.get(alert_id="A3").status == AlertStatus.PENDING


@pytest.mark.django_db
def test_auto_assignment_no_personnel(sys_user):
    _make_alert("A1")
    _make_assignment(match_type="all", personnel=[])
    operator = AlertAssignmentOperator(["A1"])
    result = operator.execute_auto_assignment()
    # 无人员配置 → 分派失败
    assert result["assigned_alerts"] == 0
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_no_active_assignments(sys_user):
    _make_alert("A1")
    # 无活跃分派策略
    operator = AlertAssignmentOperator(["A1"])
    result = operator.execute_auto_assignment()
    assert result["assigned_alerts"] == 0
