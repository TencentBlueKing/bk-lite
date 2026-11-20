"""时钟回拨后，未来的 last_run_at 不能挡住周期任务。"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from celery import Celery
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.core.celery_runtime.beat_scheduler import FutureLastRunDatabaseScheduler, FutureLastRunModelEntry
from apps.core.celery_runtime.config import BEAT_SCHEDULER

FROZEN = datetime(2026, 11, 18, 9, 0, 45, tzinfo=timezone.utc)
FIELD_LAST_RUN = datetime(2027, 4, 24, 19, 14, 0, 212994, tzinfo=timezone.utc)


def _app():
    app = Celery("future-last-run-test")
    app.conf.enable_utc = True
    app.conf.timezone = "UTC"
    return app


def _task(name, last_run_at):
    schedule = CrontabSchedule.objects.create(
        minute="*",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="UTC",
    )
    return PeriodicTask.objects.create(
        name=name,
        task="apps.alerts.tasks.tasks.check_and_send_reminders",
        crontab=schedule,
        enabled=True,
        last_run_at=last_run_at,
    )


def _entry(task, now):
    entry = FutureLastRunModelEntry(task, app=_app())
    entry._default_now = lambda: now
    entry.schedule.nowfun = lambda: now
    return entry


@pytest.mark.django_db
def test_scheduler_setting_points_at_future_last_run_entry():
    assert BEAT_SCHEDULER == "apps.core.celery_runtime.beat_scheduler.FutureLastRunDatabaseScheduler"
    assert FutureLastRunDatabaseScheduler.Entry is FutureLastRunModelEntry


@pytest.mark.django_db
def test_future_last_run_becomes_due_within_one_minute_and_persists_current_time(caplog):
    task = _task("future-last-run", FIELD_LAST_RUN)
    entry = _entry(task, FROZEN)

    with caplog.at_level(logging.WARNING, logger="celery"):
        stalled = entry.is_due()
        entry.is_due()

    assert stalled.is_due is False
    assert stalled.next <= 60
    assert entry.last_run_at == FROZEN
    task.refresh_from_db()
    assert task.last_run_at == FIELD_LAST_RUN

    warnings = [record for record in caplog.records if record.msg == "event=celery_beat_future_last_run task=%s last_run_at=%s now=%s"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.args == ("future-last-run", FIELD_LAST_RUN.isoformat(), FROZEN.isoformat())
    assert warning.getMessage() == (
        "event=celery_beat_future_last_run task=future-last-run " f"last_run_at={FIELD_LAST_RUN.isoformat()} now={FROZEN.isoformat()}"
    )
    assert warning.exc_info is None

    later = FROZEN + timedelta(seconds=61)
    entry._default_now = lambda: later
    entry.schedule.nowfun = lambda: later
    assert entry.is_due().is_due is True

    healed = next(entry)
    healed.save()
    task.refresh_from_db()
    assert task.last_run_at == later
    assert task.total_run_count == 1


@pytest.mark.django_db
def test_skew_within_tolerance_keeps_the_stored_last_run(caplog):
    now = FROZEN
    last_run_at = now + timedelta(seconds=60)
    task = _task("skew-within-tolerance", last_run_at)
    entry = _entry(task, now)

    with caplog.at_level(logging.WARNING, logger="celery"):
        state = entry.is_due()

    assert entry.last_run_at == last_run_at
    assert state.is_due is False
    assert not [record for record in caplog.records if record.msg.startswith("event=celery_beat_future_last_run")]


@pytest.mark.django_db
def test_past_last_run_stays_due_without_rewrite():
    past = FROZEN - timedelta(seconds=90)
    task = _task("past-last-run", past)
    entry = _entry(task, FROZEN)

    state = entry.is_due()

    assert state.is_due is True
    assert entry.last_run_at == past
    task.refresh_from_db()
    assert task.last_run_at == past
