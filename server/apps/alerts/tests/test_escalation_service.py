"""告警升级服务覆盖测试。

对照 spec/requirements/告警中心/20260531.告警中心-新增告警升级策略.md
"""
import pytest
from datetime import timedelta
from unittest import mock
from django.utils import timezone

from apps.alerts.models.alert_operator import AlertAssignment, AlertEscalationTask, AlertReminderTask
from apps.alerts.models.models import Alert


def _make_alert(alert_id="A1", level="0", status="pending", operator=None):
    return Alert.objects.create(
        alert_id=alert_id, level=level, title="t", content="c",
        fingerprint="fp-" + alert_id, status=status, operator=operator or [],
    )


def _chain(mode="append", layers=None):
    return {"enabled": True, "mode": mode, "layers": layers or [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20, "notify_channels": []},
    ]}


def _make_assignment(name="分派", escalation=None, channels=None, personnel=None):
    return AlertAssignment.objects.create(
        name=name, match_type="all",
        personnel=personnel or ["u1"],
        notify_channels=channels or [{"id": 1, "channel_type": "email", "name": "邮件"}],
        config={"escalation": escalation} if escalation else {},
    )


@pytest.mark.django_db
def test_escalation_task_fields_persist():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = AlertEscalationTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        mode="append", layers=_chain()["layers"],
        current_layer_index=0, layer_started_at=timezone.now(),
    )
    task.refresh_from_db()
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.layers[1]["wait_minutes"] == 20
    assert task.is_active is True


from apps.alerts.service.escalation_service import EscalationService as ES


def test_parse_escalation_config_disabled():
    assert ES.parse_escalation_config({}) is None
    assert ES.parse_escalation_config({"escalation": {"enabled": False, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}) is None


def test_parse_escalation_config_invalid_mode():
    cfg = {"escalation": {"enabled": True, "mode": "bogus", "layers": [{"personnel": ["u1"], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_empty_layers():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": []}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_missing_personnel():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": [], "wait_minutes": 5}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_layer_bad_wait():
    cfg = {"escalation": {"enabled": True, "mode": "append", "layers": [{"personnel": ["u1"], "wait_minutes": 0}]}}
    assert ES.parse_escalation_config(cfg) is None


def test_parse_escalation_config_valid():
    cfg = {"escalation": {"enabled": True, "mode": "replace", "layers": [
        {"personnel": ["u1"], "wait_minutes": 10, "notify_channels": []},
        {"personnel": ["u2"], "wait_minutes": 20},
    ]}}
    result = ES.parse_escalation_config(cfg)
    assert result["mode"] == "replace"
    assert len(result["layers"]) == 2
    assert result["layers"][1]["notify_channels"] == []  # 默认补空


def test_compute_roster_replace():
    layers = [{"personnel": ["u1"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "replace") == ["u1"]
    assert ES.compute_roster(layers, 1, "replace") == ["u2", "u3"]


def test_compute_roster_append_dedups_and_orders():
    layers = [{"personnel": ["u1", "u2"]}, {"personnel": ["u2", "u3"]}]
    assert ES.compute_roster(layers, 0, "append") == ["u1", "u2"]
    assert ES.compute_roster(layers, 1, "append") == ["u1", "u2", "u3"]


@pytest.mark.django_db
def test_create_escalation_task_none_when_disabled():
    alert = _make_alert()
    assignment = _make_assignment(escalation=None)
    assert ES.create_escalation_task(alert, assignment) is None


@pytest.mark.django_db
def test_create_escalation_task_creates_at_layer_zero():
    alert = _make_alert(operator=["existing"])
    assignment = _make_assignment(escalation=_chain(mode="append"))
    task = ES.create_escalation_task(alert, assignment)
    assert task is not None
    assert task.current_layer_index == 0
    assert task.mode == "append"
    assert task.is_active is True
    alert.refresh_from_db()
    assert "existing" in alert.operator
    assert "u1" in alert.operator


@pytest.mark.django_db
def test_create_escalation_task_idempotent_reactivates():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    first = ES.create_escalation_task(alert, assignment)
    first.is_active = False
    first.current_layer_index = 1
    first.save()
    second = ES.create_escalation_task(alert, assignment)
    assert second.alert_id == first.alert_id
    assert second.is_active is True
    assert second.current_layer_index == 0


@pytest.mark.django_db
def test_stop_escalation_task():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    ES.create_escalation_task(alert, assignment)
    assert ES.stop_escalation_task(alert) is True
    assert AlertEscalationTask.objects.get(alert=alert).is_active is False


@pytest.mark.django_db
def test_reset_escalation_task_back_to_layer_zero():
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.is_active = False
    task.save()
    reset = ES.reset_escalation_task(alert, assignment)
    assert reset.current_layer_index == 0
    assert reset.is_active is True


def _due_task(alert, assignment, index=0, minutes_ago=15):
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = index
    task.layer_started_at = timezone.now() - timedelta(minutes=minutes_ago)
    task.save()
    return task


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_advances_layer_when_deadline_passed(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain(mode="append"))
    _due_task(alert, assignment, index=0, minutes_ago=15)
    result = ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.current_layer_index == 1
    assert result["escalated"] == 1
    alert.refresh_from_db()
    assert {"u1", "u2"}.issubset(set(alert.operator))
    mock_send.assert_called_once()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_not_due_does_nothing(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    _due_task(alert, assignment, index=0, minutes_ago=3)
    ES.check_and_process_escalations()
    assert AlertEscalationTask.objects.get(alert=alert).current_layer_index == 0
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_last_layer_deactivates_no_more_escalation(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    _due_task(alert, assignment, index=1, minutes_ago=25)
    ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.current_layer_index == 1
    assert task.is_active is False
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_scan_deactivates_when_alert_not_pending(mock_send):
    alert = _make_alert(status="processing")
    assignment = _make_assignment(escalation=_chain())
    _due_task(alert, assignment, index=0, minutes_ago=15)
    ES.check_and_process_escalations()
    task = AlertEscalationTask.objects.get(alert=alert)
    assert task.is_active is False
    assert task.current_layer_index == 0
    mock_send.assert_not_called()


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService._send_escalation_notification")
def test_advance_resets_reminder_counter(mock_send):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=False,
        reminder_count=9, current_frequency_minutes=5, current_max_reminders=10,
        next_reminder_time=timezone.now(),
    )
    _due_task(alert, assignment, index=0, minutes_ago=15)
    ES.check_and_process_escalations()
    reminder = AlertReminderTask.objects.get(alert=alert)
    assert reminder.reminder_count == 0
    assert reminder.is_active is True


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_send_escalation_notification_enqueues_roster_and_channels(
    mock_delay, _mt, _mc, django_capture_on_commit_callbacks
):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(
        escalation=_chain(),
        channels=[{"id": 7, "channel_type": "wechat", "name": "企微"}],
    )
    # pytest-django wraps the test in an atomic block, so the send defers via
    # transaction.on_commit; capture+execute those callbacks to fire the enqueue.
    with django_capture_on_commit_callbacks(execute=True):
        sent = ES._send_escalation_notification(
            alert, assignment, roster=["u2", "u3"], layer_channels=[]
        )
    assert sent is True
    mock_delay.assert_called_once()
    params = mock_delay.call_args[0][0]
    assert params[0]["username_list"] == ["u2", "u3"]
    # 本层未配渠道 -> 沿用 assignment.notify_channels
    assert params[0]["channel_id"] == 7
    assert params[0]["channel_type"] == "wechat"
    assert params[0]["object_id"] == alert.alert_id


@pytest.mark.django_db
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_content", return_value="c")
@mock.patch("apps.alerts.common.notify.base.NotifyParamsFormat.format_title", return_value="t")
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_send_escalation_notification_uses_layer_channels_when_set(
    mock_delay, _mt, _mc, django_capture_on_commit_callbacks
):
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain())
    with django_capture_on_commit_callbacks(execute=True):
        sent = ES._send_escalation_notification(
            alert, assignment, roster=["u2"],
            layer_channels=[{"id": 9, "channel_type": "sms", "name": "短信"}],
        )
    assert sent is True
    params = mock_delay.call_args[0][0]
    assert params[0]["channel_id"] == 9
    assert params[0]["channel_type"] == "sms"


@pytest.mark.django_db
def test_active_roster_for_reminder_replace_mode():
    alert = _make_alert(status="pending")
    assignment = _make_assignment(escalation=_chain(mode="replace"))
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.save()
    roster, channels = ES.active_roster_for_reminder(alert)
    assert roster == ["u2"]
    assert channels is None


@pytest.mark.django_db
def test_active_roster_for_reminder_none_when_no_task():
    alert = _make_alert(status="pending")
    assert ES.active_roster_for_reminder(alert) == (None, None)


@pytest.mark.django_db(transaction=True)
@mock.patch("apps.alerts.tasks.sync_notify.delay")
def test_reminder_send_uses_escalation_roster(mock_delay):
    from apps.alerts.models.models import Level
    from apps.alerts.constants.constants import LevelType
    from apps.alerts.service.reminder_service import ReminderService

    Level.objects.get_or_create(
        level_id=0, level_type=LevelType.ALERT,
        defaults={"level_name": "Critical", "level_display_name": "严重"},
    )

    alert = _make_alert(status="pending")
    assignment = _make_assignment(
        escalation=_chain(mode="replace"),
        personnel=["orig"],
        channels=[{"id": 1, "channel_type": "email", "name": "邮件"}],
    )
    task = ES.create_escalation_task(alert, assignment)
    task.current_layer_index = 1
    task.save()
    ReminderService._send_reminder_notification(assignment=assignment, alert=alert, reminder_id=None)
    args, _ = mock_delay.call_args
    sent_usernames = args[0][0]["username_list"]
    assert sent_usernames == ["u2"]


@pytest.mark.django_db
@mock.patch("apps.alerts.service.escalation_service.EscalationService.check_and_process_escalations")
def test_celery_task_invokes_service(mock_check):
    mock_check.return_value = {"processed": 2, "escalated": 1}
    from apps.alerts.tasks.tasks import check_and_send_escalations
    result = check_and_send_escalations()
    mock_check.assert_called_once()
    assert result["escalated"] == 1


@pytest.mark.django_db
def test_cleanup_expired_escalations_deletes_old_inactive():
    from datetime import timedelta as _td
    alert = _make_alert()
    assignment = _make_assignment(escalation=_chain())
    task = ES.create_escalation_task(alert, assignment)
    task.is_active = False
    task.save()
    AlertEscalationTask.objects.filter(alert=alert).update(
        updated_at=timezone.now() - _td(days=40)
    )
    assert ES.cleanup_expired_escalations() == 1
