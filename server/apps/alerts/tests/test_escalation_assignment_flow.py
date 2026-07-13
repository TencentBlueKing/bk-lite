"""升级任务钩子集成测试：验证分派/认领/改派操作正确触发 EscalationService。

NOTE: 类名为 AlertOperator（非 AlertOperatorService），构造 AlertOperator(user="u1")。
_close_alert / _resolve_alert 不调用 _stop_reminder_tasks，故不在此测试停止升级；
只有 _acknowledge_alert 调用 _stop_reminder_tasks，对应添加了 _stop_escalation_tasks。
"""

import pytest
from unittest import mock

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask
from apps.alerts.models.models import Alert
from apps.alerts.service.alter_operator import AlertOperator


def _chain():
    return {"enabled": True, "mode": "append", "layers": [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
    ]}


@pytest.fixture
def sys_user(db):
    from apps.system_mgmt.models.user import User
    return User.objects.create(username="u1", domain="domain.com", group_list=[{"id": 1}])


@pytest.fixture
def assignment(db):
    return AlertAssignment.objects.create(
        name="esc-rule", match_type="all", personnel=["u1"],
        notify_channels=[{"id": 1, "channel_type": "email", "name": "邮件"}],
        notification_frequency={}, config={"escalation": _chain()},
    )


def _alert(status="unassigned"):
    return Alert.objects.create(
        alert_id="FA1", level="0", title="t", content="c",
        fingerprint="fp1", status=status, operator=[],
        team=[1],  # must match sys_user group_list id
    )


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_assign_creates_escalation_task(mock_delay, sys_user, assignment):
    # auto-dispatch 现在按策略 notify_channels 构造通知，会读取告警级别对应的 Level
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.models import Level

    Level.objects.get_or_create(
        level_id=0, level_type=LevelType.ALERT,
        defaults={"level_name": "critical", "level_display_name": "严重"},
    )
    alert = _alert("unassigned")
    svc = AlertOperator(user="system")
    svc._assign_alert(alert.alert_id, {"assignee": ["u1"], "assignment_id": assignment.id})
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is True
    assert task.current_layer_index == 0


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_acknowledge_stops_escalation(mock_delay, sys_user, assignment):
    alert = _alert("pending")
    alert.operator = ["u1"]
    alert.save()
    AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=True, mode="append",
        layers=_chain()["layers"], current_layer_index=0,
        layer_started_at=alert.created_at,
    )
    svc = AlertOperator(user="u1")
    svc._acknowledge_alert(alert.alert_id, {})
    assert AlertEscalationTask.objects.get(alert=alert).is_active is False


@pytest.mark.django_db
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_reassign_resets_escalation_to_layer_zero(mock_delay, sys_user, assignment):
    alert = _alert("processing")
    alert.operator = ["u1"]
    alert.save()
    AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=False, mode="append",
        layers=_chain()["layers"], current_layer_index=1,
        layer_started_at=alert.created_at,
    )
    svc = AlertOperator(user="u1")
    svc._reassign_alert(alert.alert_id, {"assignee": ["u1"], "assignment_id": assignment.id})
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is True
    assert task.current_layer_index == 0
