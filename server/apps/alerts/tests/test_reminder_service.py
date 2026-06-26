"""告警提醒服务覆盖测试。

对照 spec/prd/告警中心·告警：分派后按级别频率提醒，认领/关闭后停止提醒。
"""

import pytest

from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask
from apps.alerts.models.models import Alert
from apps.alerts.service.reminder_service import ReminderService as RS


def _make_alert(alert_id="A1", level="0"):
    return Alert.objects.create(alert_id=alert_id, level=level, title="t", content="c", fingerprint="fp")


def _make_assignment(name="分派", frequency=None):
    return AlertAssignment.objects.create(
        name=name, match_type="all", notification_frequency=frequency or {}
    )


# --------------------------------------------------------------------------
# _parse_max_count
# --------------------------------------------------------------------------


def test_parse_max_count_default_on_empty():
    assert RS._parse_max_count(None, alert_level="0", assignment_id=1) == RS.DEFAULT_MAX_REMINDERS
    assert RS._parse_max_count("", alert_level="0", assignment_id=1) == RS.DEFAULT_MAX_REMINDERS


def test_parse_max_count_zero_means_unlimited():
    assert RS._parse_max_count(0, alert_level="0", assignment_id=1) == 0


def test_parse_max_count_invalid_uses_default():
    assert RS._parse_max_count("abc", alert_level="0", assignment_id=1) == RS.DEFAULT_MAX_REMINDERS


def test_parse_max_count_negative_uses_default():
    assert RS._parse_max_count(-5, alert_level="0", assignment_id=1) == RS.DEFAULT_MAX_REMINDERS


def test_parse_max_count_valid():
    assert RS._parse_max_count(3, alert_level="0", assignment_id=1) == 3


# --------------------------------------------------------------------------
# _normalize_frequency_config
# --------------------------------------------------------------------------


def test_normalize_frequency_config_empty():
    assert RS._normalize_frequency_config({}, "0", 1) is None


def test_normalize_frequency_config_zero_interval():
    assert RS._normalize_frequency_config({"interval_minutes": 0}, "0", 1) is None


def test_normalize_frequency_config_valid():
    result = RS._normalize_frequency_config({"interval_minutes": 30, "max_count": 5}, "0", 1)
    assert result == (30, 5)


# --------------------------------------------------------------------------
# create_reminder_task
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_reminder_task_no_config_returns_none():
    alert = _make_alert()
    assignment = _make_assignment(frequency={})
    assert RS.create_reminder_task(alert, assignment) is None


@pytest.mark.django_db
def test_create_reminder_task_creates():
    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30, "max_count": 5}})
    task = RS.create_reminder_task(alert, assignment)
    assert task is not None
    assert task.current_frequency_minutes == 30
    assert task.current_max_reminders == 5
    assert task.is_active is True


@pytest.mark.django_db
def test_create_reminder_task_existing_active_returns_existing():
    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    first = RS.create_reminder_task(alert, assignment)
    second = RS.create_reminder_task(alert, assignment)
    assert first.pk == second.pk
    assert AlertReminderTask.objects.filter(alert=alert).count() == 1


@pytest.mark.django_db
def test_create_reminder_task_reactivates_inactive():
    from django.utils import timezone

    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=False,
        current_frequency_minutes=10, current_max_reminders=5, reminder_count=2,
        next_reminder_time=timezone.now(),
    )
    task = RS.create_reminder_task(alert, assignment)
    assert task.is_active is True
    assert task.reminder_count == 0
    assert task.current_frequency_minutes == 30


# --------------------------------------------------------------------------
# stop_reminder_task
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_stop_reminder_task_active():
    from django.utils import timezone

    alert = _make_alert()
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )
    assert RS.stop_reminder_task(alert) is True
    assert not AlertReminderTask.objects.filter(alert=alert, is_active=True).exists()


@pytest.mark.django_db
def test_stop_reminder_task_none_active():
    alert = _make_alert()
    assert RS.stop_reminder_task(alert) is False


# --------------------------------------------------------------------------
# _get_effective_max_reminders
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_effective_max_reminders_unlimited():
    from django.utils import timezone

    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={"0": {"max_count": 0}})
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )
    assert RS._get_effective_max_reminders(reminder) == 0


# --------------------------------------------------------------------------
# _send_reminder_notification guards
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_reminder_notification_no_personnel():
    alert = _make_alert()
    assignment = _make_assignment()
    assignment.personnel = []
    assignment.save()
    assert RS._send_reminder_notification(assignment=assignment, alert=alert) is False


@pytest.mark.django_db
def test_send_reminder_notification_no_channels():
    alert = _make_alert()
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    assignment.notify_channels = []
    assignment.save()
    assert RS._send_reminder_notification(assignment=assignment, alert=alert) is False


@pytest.mark.django_db
def test_send_reminder_notification_session_observing_skipped():
    from apps.alerts.constants.constants import SessionStatus

    alert = _make_alert()
    alert.is_session_alert = True
    alert.session_status = SessionStatus.OBSERVING
    alert.save()
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    assignment.save()
    assert RS._send_reminder_notification(assignment=assignment, alert=alert) is False


# --------------------------------------------------------------------------
# _advance_reminder_after_enqueue
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_advance_reminder_missing_returns_false():
    # 不存在的提醒任务（按 pk=alert 主键查不到）应安全返回 False。
    assert RS._advance_reminder_after_enqueue(999999) is False


@pytest.mark.django_db
def test_advance_reminder_existing_advances_count():
    """入队后推进现存提醒任务：按主键查到并自增计数。

    复现缺陷：原 filter(id=...) 会抛 FieldError 被吞掉返回 False，
    导致 reminder_count 永远不递增。修复后应返回 True 且计数 +1。
    """
    from django.utils import timezone

    from apps.alerts.constants.constants import AlertStatus

    alert = _make_alert(level="0")
    alert.status = AlertStatus.PENDING
    alert.save()
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=5, reminder_count=0,
        next_reminder_time=timezone.now(),
    )

    assert RS._advance_reminder_after_enqueue(reminder.pk) is True
    reminder.refresh_from_db()
    assert reminder.reminder_count == 1


# --------------------------------------------------------------------------
# _update_reminder_task / cleanup / search_level_map
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_reminder_task():
    from django.utils import timezone

    alert = _make_alert()
    assignment = _make_assignment()
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=10, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )
    assert RS._update_reminder_task(reminder, 60, 8) is True
    reminder.refresh_from_db()
    assert reminder.current_frequency_minutes == 60
    assert reminder.current_max_reminders == 8


@pytest.mark.django_db
def test_cleanup_expired_reminders():
    from datetime import timedelta

    from django.utils import timezone

    alert = _make_alert()
    assignment = _make_assignment()
    reminder = AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=False,
        current_frequency_minutes=10, current_max_reminders=5,
        next_reminder_time=timezone.now(),
    )
    AlertReminderTask.objects.filter(pk=reminder.pk).update(
        updated_at=timezone.now() - timedelta(days=40)
    )
    assert RS.cleanup_expired_reminders() == 1


@pytest.mark.django_db
def test_search_level_map():
    from apps.alerts.models.models import Level

    Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    result = RS.search_level_map("alert")
    assert result["0"] == "严重"


# --------------------------------------------------------------------------
# ensure_reminder_task
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_ensure_reminder_task_no_assignment_returns_none():
    alert = _make_alert()
    assert RS.ensure_reminder_task(alert) is None


@pytest.mark.django_db
def test_ensure_reminder_task_with_assignment_creates():
    alert = _make_alert(level="0")
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    task = RS.ensure_reminder_task(alert, assignment=assignment)
    assert task is not None


# --------------------------------------------------------------------------
# _send_reminder_notification success path（mock celery）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_reminder_notification_with_channels_does_not_raise():
    from apps.alerts.constants.constants import AlertStatus

    alert = _make_alert(level="0")
    alert.status = AlertStatus.PENDING
    alert.save()
    assignment = _make_assignment()
    assignment.personnel = ["op1"]
    assignment.notify_channels = [{"id": 1, "channel_type": "email"}]
    assignment.save()
    # 完整通知路径不抛异常（celery 投递在测试环境可能失败，方法内部已兜底返回 bool）
    result = RS._send_reminder_notification(assignment=assignment, alert=alert)
    assert isinstance(result, bool)


# --------------------------------------------------------------------------
# check_and_process_reminders
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_and_process_reminders_none_due():
    # 无到期提醒任务时返回零计数
    result = RS.check_and_process_reminders()
    assert result == {"processed": 0, "success": 0}


@pytest.mark.django_db
def test_check_and_process_reminders_due_task_is_processed():
    """到期的 active 提醒任务必须被处理。

    复现缺陷：AlertReminderTask 主键是 alert(OneToOne)，无 "id" 字段，
    check_and_process_reminders 用 values_list("id") 会抛 FieldError，
    被外层 try/except 吞掉后静默返回 processed=0，导致提醒永远发不出去。
    """
    from datetime import timedelta

    from django.utils import timezone

    alert = _make_alert(level="0")  # 默认 status=UNASSIGNED，处理时计入 processed 后停用
    assignment = _make_assignment(frequency={"0": {"interval_minutes": 30}})
    AlertReminderTask.objects.create(
        alert=alert, assignment=assignment, is_active=True,
        current_frequency_minutes=30, current_max_reminders=5,
        next_reminder_time=timezone.now() - timedelta(minutes=1),
    )

    result = RS.check_and_process_reminders()

    assert result["processed"] == 1
