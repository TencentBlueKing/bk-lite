import pytest
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.delivery_service import (
    DashboardReportDeliveryError,
    DashboardReportDeliveryService,
)
from apps.operation_analysis.services.execution_orchestrator import (
    DeliveryStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="测试邮件通道",
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
def wechat_channel(db):
    return Channel.objects.create(
        name="企微通道",
        channel_type="enterprise_wechat",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription_with_channel(authenticated_user, email_channel):
    directory = Directory.objects.create(name="投递测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="投递测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="投递测试订阅",
        recipient_email="recipient@example.com",
        email_channel=email_channel,
    )


@pytest.fixture
def running_execution(subscription_with_channel, email_channel):
    sub = subscription_with_channel
    execution = DashboardReportExecution.objects.create(
        subscription=sub,
        dashboard=sub.dashboard,
        creator=sub.creator,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=sub.dashboard_id,
        creator_id=sub.creator,
        creator_timezone="Asia/Shanghai",
        subscription_id=sub.id,
        subscription_name=sub.name,
        recipient_email=sub.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=email_channel.id,
        filter_values={},
    )
    assert DashboardReportExecutionService.claim_execution(execution.id)
    execution.refresh_from_db()
    return execution


@pytest.fixture
def artifact(running_execution):
    return DashboardReportPdfArtifact.objects.create(
        execution=running_execution,
        storage_reference="execution-1/report.pdf",
        filename="test_report.pdf",
        size_bytes=21,
        sha256="a" * 64,
        expires_at=timezone.now() + timedelta(hours=24),
    )


# --- email channel 权限校验 ---

class TestEmailChannelValidation:
    def test_validate_requires_channel(self, authenticated_user):
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )
        from rest_framework.exceptions import ValidationError
        from unittest.mock import MagicMock

        request = MagicMock()
        request.user = authenticated_user
        request.COOKIES = {}

        with pytest.raises(ValidationError, match="必须指定邮件通道"):
            DashboardSubscriptionService.validate_email_channel(request, None)

    def test_validate_rejects_non_email_channel(
        self, authenticated_user, wechat_channel
    ):
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )
        from rest_framework.exceptions import ValidationError
        from unittest.mock import MagicMock

        request = MagicMock()
        request.user = authenticated_user
        request.COOKIES = {}

        with pytest.raises(ValidationError, match="不是邮件类型"):
            DashboardSubscriptionService.validate_email_channel(
                request, wechat_channel
            )

    def test_validate_rejects_channel_without_team_permission(
        self, authenticated_user, email_channel
    ):
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )
        from rest_framework.exceptions import ValidationError
        from unittest.mock import MagicMock

        email_channel.team = [999]
        email_channel.save(update_fields=["team"])
        request = MagicMock(spec=[])
        request.user = authenticated_user
        request.user.is_superuser = False
        request.COOKIES = {"current_team": "1"}

        with pytest.raises(ValidationError, match="无权使用该邮件通道"):
            DashboardSubscriptionService.validate_email_channel(
                request, email_channel
            )

    def test_validate_accepts_valid_channel(
        self, authenticated_user, email_channel
    ):
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )
        from unittest.mock import MagicMock

        request = MagicMock(spec=[])
        request.user = authenticated_user
        request.user.is_superuser = False
        request.COOKIES = {"current_team": "1"}

        DashboardSubscriptionService.validate_email_channel(
            request, email_channel
        )


# --- Snapshot 冻结 channel ---

class TestSnapshotFreezesChannel:
    def test_email_channel_id_frozen_in_snapshot(
        self, running_execution, email_channel
    ):
        snapshot = running_execution.snapshot
        assert snapshot.email_channel_id == email_channel.id

    def test_snapshot_channel_isolated_from_subscription_change(
        self, running_execution, email_channel
    ):
        snapshot = running_execution.snapshot
        original_channel_id = snapshot.email_channel_id

        new_channel = Channel.objects.create(
            name="新通道",
            channel_type="email",
            config={},
            description="替换",
            team=[1],
        )
        sub = running_execution.subscription
        sub.email_channel = new_channel
        sub.save(update_fields=["email_channel_id"])

        snapshot.refresh_from_db()
        assert snapshot.email_channel_id == original_channel_id


# --- PDF artifact 不存在 / 过期 ---

class TestDeliveryArtifactChecks:
    def test_delivery_fails_when_artifact_missing(self, running_execution):
        snapshot = running_execution.snapshot
        with pytest.raises(
            DashboardReportDeliveryError, match="PDF 产物不存在"
        ):
            DashboardReportDeliveryService.deliver(
                running_execution, snapshot
            )

    def test_delivery_fails_when_artifact_expired(
        self, running_execution, artifact
    ):
        artifact.expires_at = timezone.now() - timedelta(hours=1)
        DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).update(
            expires_at=artifact.expires_at
        )
        artifact.refresh_from_db()
        snapshot = running_execution.snapshot
        with pytest.raises(
            DashboardReportDeliveryError, match="已过期"
        ):
            DashboardReportDeliveryService.deliver(
                running_execution, snapshot
            )


# --- SMTP 成功 -> succeeded / SMTP 失败 -> failed ---

class TestDeliverySmtp:
    def test_smtp_success_marks_delivered(
        self, running_execution, artifact, tmp_path
    ):
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")

        with patch(
            "apps.operation_analysis.services.delivery_service."
            "DashboardReportRenderService.resolve_artifact_path",
            return_value=pdf_file,
        ), patch(
            "apps.operation_analysis.services.delivery_service."
            "Channel.decrypt_field",
        ), patch(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            return_value={"result": True, "message": "ok"},
        ):
            snapshot = running_execution.snapshot
            DashboardReportDeliveryService.deliver(
                running_execution, snapshot
            )

        running_execution.refresh_from_db()
        assert running_execution.delivered_at is not None

    def test_smtp_failure_raises_error(
        self, running_execution, artifact, tmp_path
    ):
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")

        with patch(
            "apps.operation_analysis.services.delivery_service."
            "DashboardReportRenderService.resolve_artifact_path",
            return_value=pdf_file,
        ), patch(
            "apps.operation_analysis.services.delivery_service."
            "Channel.decrypt_field",
        ), patch(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            return_value={"result": False, "message": "SMTP connection refused"},
        ):
            snapshot = running_execution.snapshot
            with pytest.raises(
                DashboardReportDeliveryError,
                match="SMTP connection refused",
            ):
                DashboardReportDeliveryService.deliver(
                    running_execution, snapshot
                )

        running_execution.refresh_from_db()
        assert running_execution.delivered_at is None

    def test_idempotent_delivery_skips_when_already_delivered(
        self, running_execution, artifact, tmp_path
    ):
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")

        with patch(
            "apps.operation_analysis.services.delivery_service."
            "DashboardReportRenderService.resolve_artifact_path",
            return_value=pdf_file,
        ), patch(
            "apps.operation_analysis.services.delivery_service."
            "Channel.decrypt_field",
        ), patch(
            "apps.system_mgmt.utils.channel_utils.send_email_to_user",
            return_value={"result": True, "message": "ok"},
        ) as mock_send:
            snapshot = running_execution.snapshot
            DashboardReportDeliveryService.deliver(
                running_execution, snapshot
            )
            assert mock_send.call_count == 1

            DashboardReportDeliveryService.deliver(
                running_execution, snapshot
            )
            assert mock_send.call_count == 1


# --- DeliveryStep 集成 ---

class TestDeliveryStepIntegration:
    def test_delivery_step_returns_attempt_result_on_failure(
        self, running_execution
    ):
        snapshot = running_execution.snapshot
        result = DeliveryStep.execute(running_execution, snapshot)
        assert result.ok is False
        # 缺 Artifact → pdf_generate_failed，stage=render 以便 Classifier 走 RENDER
        assert result.failure_stage == "render"
        assert result.error_code == "pdf_generate_failed"


# --- 邮件时间语义（计划时间 / 手动测试；不使用 creator_timezone） ---

class TestEmailTimeSemantics:
    def test_manual_test_email_has_no_time_semantics(
        self, running_execution
    ):
        snapshot = running_execution.snapshot
        title = DashboardReportDeliveryService._build_title(
            snapshot, running_execution
        )
        html = DashboardReportDeliveryService._build_html(
            snapshot, running_execution
        )
        filename = DashboardReportRenderService._filename(
            "投递测试仪表盘",
            running_execution,
            snapshot,
        )

        assert title == "[BK-Lite] 投递测试订阅 - 手动测试"
        assert "报告计划时间" not in html
        assert "报告生成时间" not in html
        assert "created_at" not in html
        assert "手动测试" in html
        assert filename == "投递测试仪表盘_手动测试.pdf"

    def test_scheduled_email_uses_subscription_timezone_plan_time(
        self, running_execution
    ):
        from datetime import datetime, timezone as dt_timezone

        scheduled = datetime(2026, 8, 1, 1, 0, tzinfo=dt_timezone.utc)
        DashboardReportExecution.objects.filter(pk=running_execution.pk).update(
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
            scheduled_time_utc=scheduled,
        )
        running_execution.refresh_from_db()
        snapshot = running_execution.snapshot
        snapshot.trigger_type = "scheduled"
        snapshot.scheduled_time_utc = scheduled
        snapshot.schedule_timezone = "Asia/Shanghai"
        snapshot.scheduled_local_time = "2026-08-01 09:00"
        snapshot.creator_timezone = "America/New_York"

        title = DashboardReportDeliveryService._build_title(
            snapshot, running_execution
        )
        html = DashboardReportDeliveryService._build_html(
            snapshot, running_execution
        )
        filename = DashboardReportRenderService._filename(
            "投递测试仪表盘",
            running_execution,
            snapshot,
        )

        assert title == "[BK-Lite] 投递测试订阅 - 2026-08-01 09:00"
        assert "报告计划时间：2026-08-01 09:00 (Asia/Shanghai)" in html
        assert "报告生成时间" not in html
        assert "America/New_York" not in title
        assert "America/New_York" not in html
        assert filename == "投递测试仪表盘_20260801_0900.pdf"

    def test_delivery_does_not_read_creator_timezone_or_audit_timestamps(
        self, running_execution
    ):
        snapshot = running_execution.snapshot
        html = DashboardReportDeliveryService._build_html(
            snapshot, running_execution
        )
        assert "10:36" not in html
        assert str(running_execution.created_at) not in html


class TestCreatorTimezoneFreeze:
    def test_execute_freezes_creator_timezone_from_system_user(
        self, authenticated_user, email_channel, monkeypatch
    ):
        from unittest.mock import MagicMock

        from apps.operation_analysis.models.models import Dashboard, Directory
        from apps.system_mgmt.models import User as SystemUser

        SystemUser.objects.create(
            username=authenticated_user.username,
            display_name=authenticated_user.username,
            email="freeze@example.com",
            password="unused",
            domain=authenticated_user.domain,
            timezone="America/Los_Angeles",
        )
        directory = Directory.objects.create(name="时区冻结目录", groups=[1])
        dashboard = Dashboard.objects.create(
            name="时区冻结仪表盘",
            directory=directory,
            groups=[1],
            created_by=authenticated_user.username,
        )
        subscription = DashboardReportSubscription.objects.create(
            dashboard=dashboard,
            creator=authenticated_user.username,
            name="时区冻结订阅",
            recipient_email="ops@example.com",
            email_channel=email_channel,
        )
        monkeypatch.setattr(
            "apps.operation_analysis.services.subscription_service."
            "DashboardSubscriptionService.require_dashboard_view",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            DashboardReportExecutionService,
            "_dispatch_render",
            staticmethod(lambda execution_id: None),
        )
        request = MagicMock()
        request.user = authenticated_user

        execution, _created = DashboardReportExecutionService.execute_manual(
            request, subscription, request_id="tz-freeze-la"
        )

        assert execution.snapshot.creator_timezone == "America/Los_Angeles"

    def test_missing_system_user_falls_back_when_freezing(
        self, authenticated_user, email_channel, monkeypatch
    ):
        from unittest.mock import MagicMock

        from apps.operation_analysis.models.models import Dashboard, Directory

        directory = Directory.objects.create(name="缺省时区目录", groups=[1])
        dashboard = Dashboard.objects.create(
            name="缺省时区仪表盘",
            directory=directory,
            groups=[1],
            created_by=authenticated_user.username,
        )
        subscription = DashboardReportSubscription.objects.create(
            dashboard=dashboard,
            creator=authenticated_user.username,
            name="缺省时区订阅",
            recipient_email="ops@example.com",
            email_channel=email_channel,
        )
        monkeypatch.setattr(
            "apps.operation_analysis.services.subscription_service."
            "DashboardSubscriptionService.require_dashboard_view",
            lambda *args, **kwargs: None,
        )
        monkeypatch.setattr(
            DashboardReportExecutionService,
            "_dispatch_render",
            staticmethod(lambda execution_id: None),
        )
        request = MagicMock()
        request.user = authenticated_user

        execution, _created = DashboardReportExecutionService.execute_manual(
            request, subscription, request_id="tz-fallback-1"
        )

        assert execution.snapshot.creator_timezone == "Asia/Shanghai"
