from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.delivery_service import (
    classify_smtp_failure_message,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.execution_timeout_checker import (
    ExecutionTimeoutChecker,
)
from apps.operation_analysis.services.resource_state import (
    observe_resource_state,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="Outcome 通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


def _running(authenticated_user, email_channel, *, started_at=None):
    directory = Directory.objects.create(name="Outcome 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="Outcome 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="Outcome 订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=started_at or timezone.now(),
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
    return execution


class TestSmtpUnclassifiedIsTerminal:
    def test_generic_message_is_not_transient(self):
        assert classify_smtp_failure_message("Error sending email: boom") == ""
        assert classify_smtp_failure_message("421 try again later") == (
            "smtp_transient"
        )


class TestDeliveryOutcomeDurable:
    def test_observe_uses_delivery_outcome_not_error_code(
        self, authenticated_user, email_channel
    ):
        execution = _running(authenticated_user, email_channel)
        execution.error_code = "smtp_result_unknown"
        execution.save(update_fields=["error_code", "updated_at"])
        # 仅有 error_code 不得视为 smtp_unknown
        assert observe_resource_state(execution).delivery_outcome == (
            "not_delivered"
        )

        DashboardReportExecutionService.mark_delivery_outcome(
            execution,
            DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
        )
        execution.refresh_from_db()
        assert observe_resource_state(execution).delivery_outcome == (
            "smtp_unknown"
        )

    def test_timeout_does_not_fail_when_smtp_unknown_marked(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution = _running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        DashboardReportExecutionService.mark_delivery_outcome(
            execution,
            DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
        )
        action = ExecutionTimeoutChecker.converge_one(execution)
        execution.refresh_from_db()
        assert action == "unknown"
        assert execution.status == DashboardReportExecution.Status.UNKNOWN
        assert (
            execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN
        )

    def test_timeout_after_failed_then_delivered_heals_to_succeeded(
        self, authenticated_user, email_channel, monkeypatch
    ):
        """模拟 B1：timeout 先 failed，随后 SMTP 成功写入 delivery_outcome。"""
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution = _running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        # timeout 抢先
        assert ExecutionTimeoutChecker.converge_one(execution) == "failed"
        execution.refresh_from_db()
        assert execution.status == DashboardReportExecution.Status.FAILED

        # owning task 随后确认投递
        DashboardReportExecutionService.mark_delivery_outcome(
            execution,
            DashboardReportExecution.DeliveryOutcome.DELIVERED,
        )
        DashboardReportExecutionService.align_status_with_delivery_outcome(
            execution
        )
        execution.refresh_from_db()
        assert execution.status == DashboardReportExecution.Status.SUCCEEDED
        assert (
            execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.DELIVERED
        )
        assert execution.delivered_at is not None
        assert execution.error_code == ""

    def test_timeout_does_not_fail_delivered_running(
        self, authenticated_user, email_channel, monkeypatch
    ):
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_SECONDS", "60"
        )
        monkeypatch.setenv(
            "DASHBOARD_REPORT_EXECUTION_TIMEOUT_GRACE_SECONDS", "0"
        )
        execution = _running(
            authenticated_user,
            email_channel,
            started_at=timezone.now() - timedelta(minutes=5),
        )
        DashboardReportExecutionService.mark_delivery_outcome(
            execution,
            DashboardReportExecution.DeliveryOutcome.DELIVERED,
        )
        action = ExecutionTimeoutChecker.converge_one(execution)
        execution.refresh_from_db()
        assert action == "succeeded"
        assert execution.status == DashboardReportExecution.Status.SUCCEEDED
