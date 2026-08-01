import pytest
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportRenderSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.delivery_service import (
    classify_smtp_failure_message,
)
from apps.operation_analysis.services.execution_orchestrator import (
    DeliveryStep,
    ExecutionOrchestrator,
    RenderStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.retry_types import AttemptResult
from apps.system_mgmt.models import Channel, User as SystemUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="1B 邮件通道",
        channel_type="email",
        config={
            "smtp_server": "smtp.example.com",
            "port": 587,
            "smtp_user": "sender@example.com",
            "smtp_pwd": "encrypted_pwd",
            "mail_sender": "sender@example.com",
        },
        description="测试",
        team=[1],
    )


@pytest.fixture
def delivery_ready_execution(authenticated_user, email_channel, tmp_path, monkeypatch):
    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        domain=authenticated_user.domain,
        defaults={
            "display_name": authenticated_user.username,
            "email": "delivery-retry@example.com",
            "password": "unused",
            "group_list": [1],
        },
    )
    directory = Directory.objects.create(name="1B 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="1B 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        team_id=1,
        name="1B 订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        creator_domain=authenticated_user.domain,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        creator_domain=authenticated_user.domain,
        execution_team_id=1,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={},
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        dashboard_name=dashboard.name,
        dashboard_updated_at=dashboard.updated_at,
        view_sets=[],
        filters=[],
        other={},
        widget_manifest=[],
    )
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 delivery-retry")
    DashboardReportPdfArtifact.objects.create(
        execution=execution,
        storage_reference=f"execution-{execution.id}/report.pdf",
        filename="report.pdf",
        size_bytes=pdf.stat().st_size,
        sha256="b" * 64,
        expires_at=timezone.now() + timedelta(hours=24),
    )
    monkeypatch.setenv(
        "DASHBOARD_REPORT_ARTIFACT_ROOT",
        str(tmp_path),
    )
    (tmp_path / f"execution-{execution.id}").mkdir(parents=True, exist_ok=True)
    (
        tmp_path / f"execution-{execution.id}" / "report.pdf"
    ).write_bytes(pdf.read_bytes())

    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    return execution


class TestSmtpClassification:
    def test_timeout_and_permanent(self):
        assert classify_smtp_failure_message("SMTP timed out") == "smtp_timeout"
        assert (
            classify_smtp_failure_message("550 mailbox unavailable")
            == "smtp_permanent"
        )
        assert (
            classify_smtp_failure_message("421 try again later")
            == "smtp_transient"
        )
        assert (
            classify_smtp_failure_message("result unknown")
            == "smtp_result_unknown"
        )
        assert classify_smtp_failure_message("Error sending email: x") == ""


class TestDeliveryRetryIntegration:
    def test_transient_then_success_skips_render(
        self, delivery_ready_execution, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )
        render_calls = []

        def render_ok(*args, **kwargs):
            render_calls.append("render")
            return AttemptResult(ok=True, side_effect="artifact_reused")

        monkeypatch.setattr(RenderStep, "execute", render_ok)
        send_results = [
            {"result": False, "message": "421 temporary failure"},
            {"result": True, "message": "ok"},
        ]

        def fake_send(*args, **kwargs):
            return send_results.pop(0)

        monkeypatch.setattr(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            fake_send,
        )

        result = ExecutionOrchestrator.execute(delivery_ready_execution.id)
        delivery_ready_execution.refresh_from_db()

        assert result.status == DashboardReportExecution.Status.SUCCEEDED
        assert delivery_ready_execution.attempt_count == 2
        assert delivery_ready_execution.delivered_at is not None
        assert delivery_ready_execution.failure_stage == ""
        # 仅首次 full path 进入 Render；delivery resume 跳过
        assert render_calls == ["render"]

    def test_smtp_unknown_is_terminal_unknown(
        self, delivery_ready_execution, monkeypatch
    ):
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            RenderStep,
            "execute",
            lambda *args, **kwargs: AttemptResult(ok=True),
        )
        monkeypatch.setattr(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            lambda *args, **kwargs: {
                "result": False,
                "message": "smtp result unknown",
            },
        )

        result = ExecutionOrchestrator.execute(delivery_ready_execution.id)
        delivery_ready_execution.refresh_from_db()

        assert result.status == DashboardReportExecution.Status.UNKNOWN
        assert delivery_ready_execution.attempt_count == 1
        assert delivery_ready_execution.error_code == "smtp_result_unknown"
        assert (
            delivery_ready_execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN
        )
        assert delivery_ready_execution.delivered_at is None

    def test_already_delivered_short_circuits_to_success(
        self, delivery_ready_execution, monkeypatch
    ):
        DashboardReportExecutionService.mark_delivery_outcome(
            delivery_ready_execution,
            DashboardReportExecution.DeliveryOutcome.DELIVERED,
        )
        monkeypatch.setattr(
            DeliveryStep,
            "execute",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("已 delivered 不得再 Delivery")
            ),
        )
        result = ExecutionOrchestrator.execute(delivery_ready_execution.id)
        delivery_ready_execution.refresh_from_db()
        assert result.status == DashboardReportExecution.Status.SUCCEEDED
        assert (
            delivery_ready_execution.delivery_outcome
            == DashboardReportExecution.DeliveryOutcome.DELIVERED
        )

    def test_scheduled_delivery_retry_keeps_next_run_at(
        self, authenticated_user, email_channel, tmp_path, monkeypatch
    ):
        directory = Directory.objects.create(name="调度 1B", groups=[1])
        dashboard = Dashboard.objects.create(
            name="调度 1B 盘",
            directory=directory,
            groups=[1],
        )
        due_at = timezone.now() - timedelta(minutes=1)
        subscription = DashboardReportSubscription.objects.create(
            dashboard=dashboard,
            creator=authenticated_user.username,
            name="调度 1B",
            recipient_email="ops@example.com",
            email_channel=email_channel,
            schedule_type=DashboardReportSubscription.ScheduleType.DAILY,
            schedule_hour=9,
            schedule_minute=0,
            timezone="Asia/Shanghai",
            next_run_at=due_at,
            version=1,
        )
        monkeypatch.setattr(
            DashboardReportExecutionService,
            "_dispatch_render",
            staticmethod(lambda execution_id: None),
        )
        created = DashboardReportExecutionService.create_scheduled(
            subscription.id,
            now=timezone.now(),
        )
        subscription.refresh_from_db()
        advanced = subscription.next_run_at
        assert advanced > due_at

        execution = created.execution
        DashboardReportRenderSnapshot.objects.create(
            execution=execution,
            dashboard_id=dashboard.id,
            dashboard_name=dashboard.name,
            dashboard_updated_at=dashboard.updated_at,
            view_sets=[],
            filters=[],
            other={},
            widget_manifest=[],
        )
        (tmp_path / f"execution-{execution.id}").mkdir(
            parents=True, exist_ok=True
        )
        pdf = tmp_path / f"execution-{execution.id}" / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4 scheduled")
        DashboardReportPdfArtifact.objects.create(
            execution=execution,
            storage_reference=f"execution-{execution.id}/report.pdf",
            filename="report.pdf",
            size_bytes=pdf.stat().st_size,
            sha256="c" * 64,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
        assert DashboardReportExecutionService.claim_execution(execution.id)
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            RenderStep,
            "execute",
            lambda *args, **kwargs: AttemptResult(ok=True),
        )
        monkeypatch.setattr(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            lambda *args, **kwargs: {
                "result": False,
                "message": "550 permanent",
            },
        )
        ExecutionOrchestrator.execute(execution.id)
        subscription.refresh_from_db()
        assert subscription.next_run_at == advanced
