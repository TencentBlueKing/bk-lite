from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.due_subscription_scanner import (
    DueSubscriptionScanner,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.schedule_calculator import (
    ScheduleSpec,
    catch_up_scheduled_time,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="扫描邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def due_subscription(authenticated_user, email_channel):
    directory = Directory.objects.create(name="扫描目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="扫描仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    due_at = timezone.now() - timedelta(minutes=1)
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="扫描订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=due_at,
        version=1,
    )


def _catch_up_for(subscription, now):
    spec = ScheduleSpec(
        schedule_type=subscription.schedule_type,
        hour=subscription.schedule_hour,
        minute=subscription.schedule_minute,
        weekday=subscription.schedule_weekday,
        day_of_month=subscription.schedule_day_of_month,
    )
    return catch_up_scheduled_time(
        spec,
        subscription.timezone,
        stored_next_run_at=subscription.next_run_at,
        now=now,
    )


def test_create_scheduled_creates_execution_and_advances_next_run(
    due_subscription, monkeypatch, django_capture_on_commit_callbacks
):
    dispatch = MagicMock()
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        dispatch,
    )
    now = timezone.now()
    expected = _catch_up_for(due_subscription, now)
    with django_capture_on_commit_callbacks(execute=True):
        result = DashboardReportExecutionService.create_scheduled(
            due_subscription.id,
            now=now,
        )
    assert result.created is True
    assert result.execution is not None
    assert result.execution.trigger_type == "scheduled"
    assert result.execution.scheduled_time_utc == expected
    snapshot = result.execution.snapshot
    assert snapshot.scheduled_time_utc == expected
    assert snapshot.schedule_timezone == "Asia/Shanghai"
    assert snapshot.scheduled_local_time
    assert snapshot.subscription_version == 1

    due_subscription.refresh_from_db()
    assert due_subscription.next_run_at > now
    assert due_subscription.next_run_at > expected
    dispatch.assert_called_once_with(result.execution.id)


def test_create_scheduled_skips_when_in_flight(
    due_subscription, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    DashboardReportExecution.objects.create(
        subscription=due_subscription,
        dashboard=due_subscription.dashboard,
        creator=due_subscription.creator,
        trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
        request_id="inflight-1",
        status=DashboardReportExecution.Status.PENDING,
    )
    original_next = due_subscription.next_run_at
    result = DashboardReportExecutionService.create_scheduled(
        due_subscription.id,
        now=timezone.now(),
    )
    assert result.skipped_in_flight is True
    assert result.created is False
    due_subscription.refresh_from_db()
    assert due_subscription.next_run_at == original_next


def test_snapshot_failure_marks_execution_failed_and_advances_next_run(
    due_subscription, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    now = timezone.now()

    def boom(*args, **kwargs):
        raise RuntimeError("snapshot broken")

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_create_snapshot",
        boom,
    )

    result = DashboardReportExecutionService.create_scheduled(
        due_subscription.id,
        now=now,
    )

    assert result.created is True
    assert result.execution is not None
    result.execution.refresh_from_db()
    assert result.execution.status == DashboardReportExecution.Status.FAILED
    assert result.execution.failure_stage == "snapshot"

    due_subscription.refresh_from_db()
    assert due_subscription.next_run_at is not None
    assert due_subscription.next_run_at > now


def test_scanner_ignores_unscheduled_subscriptions(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="无调度目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="无调度仪表盘",
        directory=directory,
        groups=[1],
    )
    DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="无调度",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=None,
        next_run_at=None,
    )
    stats = DueSubscriptionScanner.scan(now=timezone.now())
    assert stats.scanned == 0
    assert stats.created == 0


def test_scanner_creates_due_subscription(due_subscription, monkeypatch):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    stats = DueSubscriptionScanner.scan(now=timezone.now())
    assert stats.scanned == 1
    assert stats.created == 1
    assert DashboardReportExecution.objects.filter(
        subscription=due_subscription,
        trigger_type="scheduled",
    ).count() == 1


def test_scanner_does_not_call_orchestrator(due_subscription, monkeypatch):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    orchestrator = MagicMock()
    monkeypatch.setattr(
        "apps.operation_analysis.services.execution_orchestrator."
        "ExecutionOrchestrator.execute",
        orchestrator,
    )
    DueSubscriptionScanner.scan(now=timezone.now())
    orchestrator.assert_not_called()


def test_scanner_can_create_next_cycle_after_snapshot_failure(
    due_subscription, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    now = timezone.now()

    first_call = {"done": False}
    original_create_snapshot = DashboardReportExecutionService._create_snapshot

    def flaky_snapshot(*args, **kwargs):
        if not first_call["done"]:
            first_call["done"] = True
            raise RuntimeError("snapshot broken")
        return original_create_snapshot(*args, **kwargs)

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_create_snapshot",
        flaky_snapshot,
    )

    first = DueSubscriptionScanner.scan(now=now)
    assert first.created == 1

    due_subscription.refresh_from_db()
    next_cycle = due_subscription.next_run_at
    assert next_cycle is not None
    assert next_cycle > now

    second = DueSubscriptionScanner.scan(now=next_cycle)
    assert second.created == 1
    assert (
        DashboardReportExecution.objects.filter(
            subscription=due_subscription,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        ).count()
        == 2
    )


def test_same_scheduled_time_is_not_created_twice_after_snapshot_failure(
    due_subscription, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    now = timezone.now()
    expected = _catch_up_for(due_subscription, now)

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_create_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("snapshot broken")
        ),
    )

    first = DashboardReportExecutionService.create_scheduled(
        due_subscription.id,
        now=now,
    )
    assert first.created is True
    assert first.execution.scheduled_time_utc == expected

    second = DashboardReportExecutionService.create_scheduled(
        due_subscription.id,
        now=now,
    )
    assert second.created is False
    assert second.already_exists is False
    assert (
        DashboardReportExecution.objects.filter(
            subscription=due_subscription,
            scheduled_time_utc=expected,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        ).count()
        == 1
    )


def test_beat_schedule_registers_scan_task():
    from apps.operation_analysis.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE["scan_due_dashboard_report_subscriptions"]
    assert (
        entry["task"]
        == "operation_analysis.scan_due_dashboard_report_subscriptions"
    )
    timeout_entry = CELERY_BEAT_SCHEDULE[
        "converge_timed_out_dashboard_report_executions"
    ]
    assert (
        timeout_entry["task"]
        == "operation_analysis.converge_timed_out_dashboard_report_executions"
    )
    assert entry["schedule"]._orig_minute == "*"
    assert timeout_entry["schedule"]._orig_minute == "*"


def test_manual_execute_does_not_change_next_run_at(
    due_subscription, authenticated_user, monkeypatch
):
    from types import SimpleNamespace

    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.subscription_service."
        "DashboardSubscriptionService.require_canvas_view",
        lambda *args, **kwargs: None,
    )
    original = due_subscription.next_run_at
    request = SimpleNamespace(
        user=authenticated_user,
        data={"request_id": "manual-keep-schedule"},
    )
    DashboardReportExecutionService.execute_manual(
        request, due_subscription, request_id="manual-keep-schedule"
    )
    due_subscription.refresh_from_db()
    assert due_subscription.next_run_at == original


def test_daily_outage_three_days_creates_only_one_execution(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="补偿目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="补偿仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    stored = datetime(2026, 8, 1, 1, 0, tzinfo=dt_timezone.utc)
    now = datetime(2026, 8, 4, 2, 0, tzinfo=dt_timezone.utc)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="三日停机",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=stored,
        version=1,
    )

    stats = DueSubscriptionScanner.scan(now=now)
    assert stats.scanned == 1
    assert stats.created == 1
    executions = list(
        DashboardReportExecution.objects.filter(
            subscription=sub,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        )
    )
    assert len(executions) == 1
    assert executions[0].scheduled_time_utc == datetime(
        2026, 8, 4, 1, 0, tzinfo=dt_timezone.utc
    )
    sub.refresh_from_db()
    assert sub.next_run_at == datetime(
        2026, 8, 5, 1, 0, tzinfo=dt_timezone.utc
    )
    assert sub.next_run_at > now

    # 同一次扫描语义：再次扫描不因陈旧历史再补多期
    again = DueSubscriptionScanner.scan(now=now)
    assert again.created == 0
    assert (
        DashboardReportExecution.objects.filter(subscription=sub).count()
        == 1
    )


def test_weekly_outage_cross_week_creates_only_one_execution(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="周补偿目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="周补偿仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    stored = datetime(2026, 8, 3, 1, 0, tzinfo=dt_timezone.utc)
    now = datetime(2026, 8, 13, 2, 0, tzinfo=dt_timezone.utc)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="跨周停机",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.WEEKLY,
        schedule_weekday=0,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=stored,
        version=1,
    )

    stats = DueSubscriptionScanner.scan(now=now)
    assert stats.created == 1
    execution = DashboardReportExecution.objects.get(subscription=sub)
    assert execution.scheduled_guard is True
    assert execution.scheduled_time_utc == datetime(
        2026, 8, 10, 1, 0, tzinfo=dt_timezone.utc
    )
    sub.refresh_from_db()
    assert sub.next_run_at == datetime(
        2026, 8, 17, 1, 0, tzinfo=dt_timezone.utc
    )


def test_monthly_day_31_outage_creates_only_one_execution(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="月末补偿目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="月末补偿仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    stored = datetime(2026, 1, 31, 1, 0, tzinfo=dt_timezone.utc)
    now = datetime(2026, 4, 15, 2, 0, tzinfo=dt_timezone.utc)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="月末31",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.MONTHLY,
        schedule_day_of_month=31,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=stored,
        version=1,
    )

    stats = DueSubscriptionScanner.scan(now=now)
    assert stats.created == 1
    execution = DashboardReportExecution.objects.get(subscription=sub)
    assert execution.scheduled_time_utc == datetime(
        2026, 3, 31, 1, 0, tzinfo=dt_timezone.utc
    )
    sub.refresh_from_db()
    assert sub.next_run_at > now
    assert sub.next_run_at.astimezone(dt_timezone.utc).month == 4


def test_dst_outage_creates_only_one_execution(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="DST目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="DST仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    stored = datetime(2026, 3, 7, 7, 30, tzinfo=dt_timezone.utc)
    now = datetime(2026, 3, 9, 14, 0, tzinfo=dt_timezone.utc)
    sub = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="DST补偿",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=2,
        schedule_minute=30,
        timezone="America/New_York",
        next_run_at=stored,
        version=1,
    )

    stats = DueSubscriptionScanner.scan(now=now)
    assert stats.created == 1
    assert (
        DashboardReportExecution.objects.filter(subscription=sub).count()
        == 1
    )
    execution = DashboardReportExecution.objects.get(subscription=sub)
    assert execution.scheduled_time_utc == datetime(
        2026, 3, 9, 6, 30, tzinfo=dt_timezone.utc
    )
    sub.refresh_from_db()
    assert sub.next_run_at > now


def test_dual_scanner_concurrent_create_only_one_execution(
    due_subscription, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    now = timezone.now()
    first = DueSubscriptionScanner.scan(now=now)
    second = DueSubscriptionScanner.scan(now=now)
    assert first.created == 1
    assert second.created == 0
    assert (
        DashboardReportExecution.objects.filter(
            subscription=due_subscription,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
        ).count()
        == 1
    )


def test_scanner_skips_paused_and_deleted(
    authenticated_user, email_channel, monkeypatch
):
    monkeypatch.setattr(
        DashboardReportExecutionService,
        "_dispatch_render",
        MagicMock(),
    )
    directory = Directory.objects.create(name="跳过目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="跳过仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    due = timezone.now() - timedelta(hours=1)
    paused = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="已暂停",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=due,
        status=DashboardReportSubscription.Status.PAUSED,
        version=1,
    )
    deleted = DashboardReportSubscription.all_objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="已删除",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=due,
        deleted_at=timezone.now(),
        version=1,
    )
    stats = DueSubscriptionScanner.scan(now=timezone.now())
    assert stats.scanned == 0
    assert (
        DashboardReportExecution.objects.filter(
            subscription_id__in=[paused.id, deleted.id]
        ).count()
        == 0
    )
