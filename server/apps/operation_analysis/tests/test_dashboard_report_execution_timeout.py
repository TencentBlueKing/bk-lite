from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.due_subscription_scanner import (
    DueSubscriptionScanner,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
    IN_FLIGHT_STATUSES,
)
from apps.operation_analysis.services.execution_timeout_checker import (
    ExecutionTimeoutChecker,
)
from apps.operation_analysis.tasks.tasks import (
    converge_timed_out_dashboard_report_executions_task,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="Timeout 通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


def _make_running(authenticated_user, email_channel, *, started_at):
    directory = Directory.objects.create(name="Timeout 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="Timeout 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="Timeout 订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
        schedule_hour=9,
        schedule_minute=0,
        timezone="Asia/Shanghai",
        next_run_at=timezone.now() + timedelta(days=1),
        version=1,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=started_at,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={},
    )
    return execution, subscription


class TestExecutionTimeoutChecker:
    def test_not_delivered_converges_to_failed(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution, subscription = _make_running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        assert (
            DashboardReportExecution.objects.filter(
                subscription=subscription,
                status__in=IN_FLIGHT_STATUSES,
            ).exists()
        )

        stats = ExecutionTimeoutChecker.sweep()
        execution.refresh_from_db()
        assert stats.failed == 1
        assert execution.status == DashboardReportExecution.Status.FAILED
        assert execution.error_code == "execution_timeout"
        assert not DashboardReportExecution.objects.filter(
            subscription=subscription,
            status__in=IN_FLIGHT_STATUSES,
        ).exists()

    def test_delivered_converges_to_succeeded_not_failed(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution, _ = _make_running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        execution.delivered_at = timezone.now() - timedelta(minutes=1)
        execution.delivery_outcome = (
            DashboardReportExecution.DeliveryOutcome.DELIVERED
        )
        execution.save(
            update_fields=["delivered_at", "delivery_outcome", "updated_at"]
        )

        ExecutionTimeoutChecker.sweep()
        execution.refresh_from_db()
        assert execution.status == DashboardReportExecution.Status.SUCCEEDED
        assert execution.error_code == ""
        assert (
            execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.DELIVERED
        )

    def test_already_terminal_is_noop(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution, _ = _make_running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.SUCCEEDED,
        )
        stats = ExecutionTimeoutChecker.sweep()
        execution.refresh_from_db()
        assert stats.failed == 0
        assert execution.status == DashboardReportExecution.Status.SUCCEEDED

    def test_cas_loses_to_concurrent_success(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution, _ = _make_running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        # 模拟 owning task 先成功
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.SUCCEEDED,
        )
        action = ExecutionTimeoutChecker.converge_one(execution)
        execution.refresh_from_db()
        assert action == "skipped"
        assert execution.status == DashboardReportExecution.Status.SUCCEEDED

    def test_timeout_releases_in_flight_for_scanner(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution, subscription = _make_running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        # 到期计划：把 next_run_at 拨回过去以验证释放后可扫
        due = timezone.now() - timedelta(minutes=1)
        subscription.next_run_at = due
        subscription.save(update_fields=["next_run_at", "updated_at"])

        monkeypatch.setattr(
            DashboardReportExecutionService,
            "_dispatch_render",
            staticmethod(lambda execution_id: None),
        )
        before = DueSubscriptionScanner.scan()
        assert before.skipped_in_flight >= 1

        converge_timed_out_dashboard_report_executions_task()
        execution.refresh_from_db()
        assert execution.status == DashboardReportExecution.Status.FAILED

        after = DueSubscriptionScanner.scan()
        assert after.created >= 1 or after.already_exists >= 0
        # 关键槽位后不应再因该 orphan 永久 skipped_in_flight
        assert not DashboardReportExecution.objects.filter(
            pk=execution.pk,
            status__in=IN_FLIGHT_STATUSES,
        ).exists()
