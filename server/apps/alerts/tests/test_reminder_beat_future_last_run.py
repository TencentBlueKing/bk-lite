"""未来的 Beat last_run_at 放行后，已到期的待响应催办才发出。"""

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from celery import Celery
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models import AlertOutbox
from apps.alerts.models.alert_operator import AlertAssignment, AlertReminderTask
from apps.alerts.models.models import Alert
from apps.alerts.service.reminder_service import ReminderService
from apps.core.celery_runtime.beat_scheduler import FutureLastRunModelEntry

FROZEN = datetime(2026, 11, 18, 9, 0, 45, tzinfo=dt_timezone.utc)
FIELD_LAST_RUN = datetime(2027, 4, 24, 19, 14, 0, 212994, tzinfo=dt_timezone.utc)


def _entry(now, last_run_at, name):
    schedule = CrontabSchedule.objects.create(
        minute="*",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    task = PeriodicTask.objects.create(
        name=name,
        task="apps.alerts.tasks.tasks.check_and_send_reminders",
        crontab=schedule,
        enabled=True,
        last_run_at=last_run_at,
    )
    app = Celery("reminder-beat-test")
    app.conf.enable_utc = True
    app.conf.timezone = "UTC"
    entry = FutureLastRunModelEntry(task, app=app)
    entry._default_now = lambda current=now: current
    entry.schedule.nowfun = lambda current=now: current
    return entry


@pytest.mark.django_db(transaction=True)
def test_due_pending_reminder_sends_after_future_last_run_is_released(monkeypatch):
    alert = Alert.objects.create(
        alert_id="ALERT-96944AD9D880461F888F23CBFDF55A0A",
        level="0",
        status=AlertStatus.PENDING,
        title="t",
        content="c",
        fingerprint="fp-stall",
    )
    assignment = AlertAssignment.objects.create(
        name="告警分派-周期催办",
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
        next_reminder_time=timezone.now() - timedelta(hours=29),
    )
    captured = {}

    def fake_build(*args, **kwargs):
        captured["scene"] = kwargs.get("scene")
        return [
            {"channel_id": 2, "channel_type": "enterprise_wechat_bot"},
            {"channel_id": 3, "channel_type": "enterprise_wechat_bot"},
        ]

    monkeypatch.setattr(
        "apps.alerts.service.escalation_service.EscalationService.active_roster_for_reminder",
        staticmethod(lambda _alert: (None, None)),
    )
    monkeypatch.setattr("apps.alerts.common.notify.dispatcher.build_channel_params", fake_build)
    monkeypatch.setattr("apps.alerts.tasks.deliver_alert_outbox.delay", lambda _pk: None)

    entry = _entry(FROZEN, FIELD_LAST_RUN, "reminder-beat")
    assert entry.is_due().is_due is False
    reminder.refresh_from_db()
    assert reminder.reminder_count == 0
    assert AlertOutbox.objects.count() == 0

    later = FROZEN + timedelta(seconds=61)
    entry._default_now = lambda: later
    entry.schedule.nowfun = lambda: later
    assert entry.is_due().is_due is True

    result = ReminderService.check_and_process_reminders()

    reminder.refresh_from_db()
    assert result == {"processed": 1, "success": 1}
    assert reminder.reminder_count == 1
    assert captured["scene"] == "reminder"
    outbox = AlertOutbox.objects.get()
    assert outbox.idempotency_key == f"reminder:{reminder.pk}:1"
    assert len(outbox.payload["params"]) == 2
