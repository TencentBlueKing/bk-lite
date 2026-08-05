"""恢复通知服务覆盖测试。

分派策略勾选【恢复】(notification_scenario 含 "recovery") 时，
alert 状态变为 AUTO_RECOVERY 后按策略 channels + personnel 发【恢复】前缀通知。
"""
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask
from apps.alerts.models.models import Alert
from apps.alerts.service.recovery_notify import notify_alert_recovered


def _make_alert(alert_id="A-R1"):
    return Alert.objects.create(
        alert_id=alert_id, level="0", title="t", content="c",
        fingerprint="fp", team=[1],
    )


def _make_assignment(name="分派", scenario=None, channels=None, personnel=None):
    return AlertAssignment.objects.create(
        name=name, match_type="all",
        notification_scenario=scenario if scenario is not None else ["recovery"],
        notify_channels=channels if channels is not None else [{"id": 3, "channel_type": "email"}],
        personnel=personnel if personnel is not None else ["op1"],
    )


def _bind_reminder(alert, assignment, is_active=True):
    return AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=is_active,
        current_frequency_minutes=30, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )


@pytest.mark.django_db
def test_notify_alert_recovered_no_assignment_returns_false():
    alert = _make_alert()
    assert notify_alert_recovered(alert) is False


@pytest.mark.django_db
def test_notify_alert_recovered_scenario_missing_recovery_returns_false():
    alert = _make_alert()
    assignment = _make_assignment(scenario=["assignment"])
    _bind_reminder(alert, assignment)
    assert notify_alert_recovered(alert) is False


@pytest.mark.django_db
def test_notify_alert_recovered_no_personnel_returns_false():
    alert = _make_alert()
    assignment = _make_assignment(personnel=[])
    _bind_reminder(alert, assignment)
    assert notify_alert_recovered(alert) is False


@pytest.mark.django_db
def test_notify_alert_recovered_no_channels_returns_false():
    alert = _make_alert()
    assignment = _make_assignment(channels=[])
    _bind_reminder(alert, assignment)
    assert notify_alert_recovered(alert) is False


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="【严重】t")
@mock.patch("apps.alerts.common.notify.dispatcher.enqueue_notifications", return_value=True)
def test_notify_alert_recovered_enqueues_with_recovery_prefix(mock_enqueue, _mt, _mc):
    alert = _make_alert()
    assignment = _make_assignment()
    _bind_reminder(alert, assignment)

    assert notify_alert_recovered(alert) is True

    assert mock_enqueue.called
    params = mock_enqueue.call_args.args[0]
    assert len(params) == 1
    assert params[0]["title"] == "【恢复】【严重】t"
    assert params[0]["content"] == "正文"
    assert params[0]["username_list"] == ["op1"]
    assert params[0]["channel_type"] == "email"
    assert params[0]["channel_id"] == 3
    assert params[0]["object_id"] == alert.alert_id
    assert mock_enqueue.call_args.kwargs["idempotency_key"] == f"recovery-notify:{alert.alert_id}"


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="正文")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="【严重】t")
@mock.patch("apps.alerts.common.notify.dispatcher.enqueue_notifications", return_value=True)
def test_notify_alert_recovered_uses_inactive_reminder_task(mock_enqueue, _mt, _mc):
    """stop_reminder_task 已把 is_active 置 False 也要能找到 assignment。"""
    alert = _make_alert()
    assignment = _make_assignment()
    _bind_reminder(alert, assignment, is_active=False)

    assert notify_alert_recovered(alert) is True
    assert mock_enqueue.called
