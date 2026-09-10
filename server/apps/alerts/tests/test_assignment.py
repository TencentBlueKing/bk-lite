"""告警自动分派覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：分派策略在生效时间内匹配未分派告警并分派给指定人员。
"""

import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.common.assignment import AlertAssignmentOperator, execute_auto_assignment_for_alerts
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlertAssignment
from apps.alerts.models.models import Alert
from apps.system_mgmt.models import Group


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User

    return User.objects.create(username="op1", domain="domain.com", group_list=[{"id": 1}])


def _make_alert(alert_id="A1", status=AlertStatus.UNASSIGNED, **over):
    defaults = dict(
        alert_id=alert_id,
        level="0",
        title="CPU高",
        content="c",
        fingerprint="fp" + alert_id,
        status=status,
        source_name="prometheus",
        team=[1],
    )
    defaults.update(over)
    return Alert.objects.create(**defaults)


def _make_assignment(name="分派", match_type="all", **over):
    defaults = dict(
        name=name,
        match_type=match_type,
        is_active=True,
        personnel=["op1"],
        match_rules=[],
        config={},
        notify_channels=[],
        notification_scenario=[],
        notification_frequency={},
    )
    defaults.update(over)
    return AlertAssignment.objects.create(**defaults)


@pytest.mark.django_db
def test_assignment_operator_no_alerts_is_terminal_warning(caplog):
    """全部 alert_id 查无此行属终态（历史残留 outbox 记录）：WARNING + 零值结果，不 raise。"""
    caplog.set_level(logging.DEBUG, logger="alert")
    operator = AlertAssignmentOperator(["nonexistent"])
    assert operator.alerts == {}
    assert "nonexistent" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    result = operator.execute_auto_assignment()
    assert result["total_alerts"] == 0
    assert result["assigned_alerts"] == 0


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
    operator.execute_auto_assignment()
    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_level_or_matches_either_enum(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "any_of", "value": ["0"]}], [{"key": "level", "operator": "any_of", "value": ["1"]}]],
    )

    AlertAssignmentOperator(["A1", "A2", "A3"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A3").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_level_and_excludes_both_enums(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "none_of", "value": ["0"]}, {"key": "level", "operator": "none_of", "value": ["1"]}]],
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
def test_auto_assignment_rejected_operation_is_not_counted_as_success(sys_user):
    """操作层明确拒绝分派时，统计不得伪报成功。"""
    alert = _make_alert("A1")
    _make_assignment(match_type="all", personnel=["missing-user"])

    result = AlertAssignmentOperator([alert.alert_id]).execute_auto_assignment()

    alert.refresh_from_db()
    assert result["assigned_alerts"] == 0
    assert result["failed_alerts"] == 1
    assert alert.status == AlertStatus.UNASSIGNED
    assert alert.operator == []


@pytest.mark.django_db
def test_auto_assignment_resolves_organization_members(sys_user):
    group = Group.objects.create(name="值班组")
    sys_user.group_list = [group.id]
    sys_user.save(update_fields=["group_list"])
    _make_alert("A1", status=AlertStatus.UNASSIGNED, team=[group.id])
    _make_assignment(
        match_type="all",
        personnel=[],
        config={
            "notification_target": {
                "type": "organization",
                "organization_ids": [group.id],
                "include_children": False,
            }
        },
    )

    result = AlertAssignmentOperator(["A1"]).execute_auto_assignment()

    alert = Alert.objects.get(alert_id="A1")
    assert result["assigned_alerts"] == 1
    assert alert.status == AlertStatus.PENDING
    assert alert.operator == ["op1"]


@pytest.mark.django_db
def test_auto_assignment_accepts_child_members_when_target_includes_children(
    sys_user,
):
    parent = Group.objects.create(name="运维中心")
    child = Group.objects.create(name="一线值班", parent_id=parent.id)
    sys_user.group_list = [child.id]
    sys_user.save(update_fields=["group_list"])
    _make_alert("A1", status=AlertStatus.UNASSIGNED, team=[parent.id])
    _make_assignment(
        match_type="all",
        personnel=[],
        config={
            "notification_target": {
                "type": "organization",
                "organization_ids": [parent.id],
                "include_children": True,
            }
        },
    )

    result = AlertAssignmentOperator(["A1"]).execute_auto_assignment()

    assert result["assigned_alerts"] == 1
    assert Alert.objects.get(alert_id="A1").operator == ["op1"]


@pytest.mark.django_db
def test_auto_assignment_no_active_assignments(sys_user):
    _make_alert("A1")
    # 无活跃分派策略
    operator = AlertAssignmentOperator(["A1"])
    result = operator.execute_auto_assignment()
    assert result["assigned_alerts"] == 0


@pytest.mark.django_db
def test_equal_priority_prefers_newer_assignment(sys_user):
    alert = _make_alert("A-NEWER")
    older = _make_assignment(name="较早创建", priority=50)
    newer = _make_assignment(name="较晚创建", priority=50)
    now = timezone.now()
    AlertAssignment.objects.filter(pk=older.pk).update(created_at=now - timedelta(minutes=1))
    AlertAssignment.objects.filter(pk=newer.pk).update(created_at=now)

    result = AlertAssignmentOperator([alert.alert_id]).execute_auto_assignment()

    assert result["assignment_results"][0]["assignment_id"] == newer.id


@pytest.mark.django_db
def test_equal_priority_and_created_at_prefers_larger_id(sys_user):
    alert = _make_alert("A-LARGER-ID")
    smaller_id = _make_assignment(name="较小ID", priority=50)
    larger_id = _make_assignment(name="较大ID", priority=50)
    same_created_at = timezone.now()
    AlertAssignment.objects.filter(pk__in=[smaller_id.pk, larger_id.pk]).update(created_at=same_created_at)

    result = AlertAssignmentOperator([alert.alert_id]).execute_auto_assignment()

    assert result["assignment_results"][0]["assignment_id"] == larger_id.id
