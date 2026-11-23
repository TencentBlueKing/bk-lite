"""对照现场缺陷：旧调度停在 2027，新调度在 61 秒后放行催办。"""

from datetime import datetime, timedelta, timezone

import pytest
from celery import Celery
from django.utils import timezone as dj_timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django_celery_beat.schedulers import ModelEntry

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask
from apps.alerts.models.models import Alert
from apps.alerts.service.reminder_service import ReminderService
from apps.core.celery_runtime.beat_scheduler import FutureLastRunModelEntry

FROZEN = datetime(2026, 11, 18, 9, 0, 45, tzinfo=timezone.utc)
FIELD_LAST_RUN = datetime(2027, 4, 24, 19, 14, 0, 212994, tzinfo=timezone.utc)


def _app():
    app = Celery("field-defect-compare")
    app.conf.enable_utc = True
    app.conf.timezone = "UTC"
    return app


def _freeze(entry, now):
    entry._default_now = lambda current=now: current
    entry.schedule.nowfun = lambda current=now: current
    return entry


@pytest.mark.django_db(transaction=True)
def test_field_defect_stock_scheduler_stays_blocked_and_fix_sends(monkeypatch):
    schedule = CrontabSchedule.objects.create(
        minute="*",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    task = PeriodicTask.objects.create(
        name="check_and_send_reminders",
        task="apps.alerts.tasks.tasks.check_and_send_reminders",
        crontab=schedule,
        enabled=True,
        last_run_at=FIELD_LAST_RUN,
        total_run_count=12961,
    )
    alert = Alert.objects.create(
        alert_id="ALERT-96944AD9D880461F888F23CBFDF55A0A",
        level="0",
        status=AlertStatus.PENDING,
        title="t",
        content="c",
        fingerprint="fp-stall",
    )
    assignment = AlertAssignment.objects.create(
        name="告警分派-现场对照",
        match_type="all",
        personnel=["admin"],
        notify_channels=[
            {"id": 2, "channel_type": "enterprise_wechat_bot"},
            {"id": 3, "channel_type": "enterprise_wechat_bot"},
        ],
        notification_frequency={"0": {"interval_minutes": 10, "max_count": 0}},
    )
    reminder = AlertReminderTask.objects.create(
        alert=alert,
        assignment=assignment,
        is_active=True,
        reminder_count=0,
        current_frequency_minutes=10,
        current_max_reminders=0,
        next_reminder_time=dj_timezone.now() - timedelta(hours=29),
    )
    monkeypatch.setattr(
        "apps.alerts.service.escalation_service.EscalationService.active_roster_for_reminder",
        staticmethod(lambda _alert: (["admin"], None)),
    )
    monkeypatch.setattr(
        "apps.alerts.common.notify.dispatcher.build_channel_params",
        lambda *args, **kwargs: [{"channel_id": 2, "channel_type": "enterprise_wechat_bot", "scene": kwargs.get("scene")}],
    )
    monkeypatch.setattr("apps.alerts.tasks.deliver_alert_outbox.delay", lambda _pk: None)

    app = _app()
    stock = _freeze(ModelEntry(task, app=app), FROZEN)
    stock_now = stock.is_due()
    stock_later = _freeze(ModelEntry(task, app=app), FROZEN + timedelta(seconds=61)).is_due()

    fixed = _freeze(FutureLastRunModelEntry(task, app=app), FROZEN)
    fixed_now = fixed.is_due()
    later = FROZEN + timedelta(seconds=61)
    _freeze(fixed, later)
    fixed_later = fixed.is_due()

    before = ReminderService.check_and_process_reminders() if fixed_now.is_due else {"processed": 0, "success": 0}
    sent = ReminderService.check_and_process_reminders() if fixed_later.is_due else {"processed": 0, "success": 0}
    reminder.refresh_from_db()

    assert stock_now.is_due is False
    assert stock_now.next > 13600000
    assert stock_later.is_due is False
    assert stock_later.next > 13600000
    assert fixed_now.is_due is False
    assert fixed_now.next <= 60
    assert fixed_later.is_due is True
    assert before == {"processed": 0, "success": 0}
    assert sent == {"processed": 1, "success": 1}
    assert reminder.reminder_count == 1
    assert reminder.last_reminder_time is not None
