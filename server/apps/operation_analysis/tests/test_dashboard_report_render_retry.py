import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
    DashboardReportRenderToken,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
    RenderStep,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.render_token_service import (
    DashboardReportRenderTokenError,
    DashboardReportRenderTokenService,
)
from apps.operation_analysis.services.retry_types import AttemptResult
from apps.system_mgmt.models import Channel
from apps.system_mgmt.models import User as SystemUser


pytestmark = pytest.mark.django_db


@pytest.fixture
def running_execution(authenticated_user):
    SystemUser.objects.get_or_create(
        username=authenticated_user.username,
        defaults={
            "display_name": authenticated_user.username,
            "email": "token-retry@example.com",
            "password": "unused",
            "domain": authenticated_user.domain,
            "group_list": authenticated_user.group_list,
        },
    )
    directory = Directory.objects.create(name="Token Retry 目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="Token Retry 仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    channel = Channel.objects.create(
        name="Token Retry 通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="Token Retry 订阅",
        recipient_email="ops@example.com",
        email_channel=channel,
    )
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=dashboard,
        creator=authenticated_user.username,
        status=DashboardReportExecution.Status.RUNNING,
        started_at=timezone.now(),
        attempt_count=1,
    )
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=dashboard.id,
        creator_id=authenticated_user.username,
        subscription_id=subscription.id,
        subscription_name=subscription.name,
        recipient_email=subscription.recipient_email,
        trigger_type=execution.trigger_type,
        email_channel_id=channel.id,
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
    return execution


class TestAttemptLevelRenderToken:
    def test_reissue_invalidates_previous_plaintext(
        self, running_execution, monkeypatch
    ):
        monkeypatch.setenv("SECRET_KEY", "token-retry-secret")
        first = DashboardReportRenderTokenService.issue(
            running_execution, attempt_no=1
        )
        second = DashboardReportRenderTokenService.issue(
            running_execution, attempt_no=2
        )
        record = DashboardReportRenderToken.objects.get(
            execution=running_execution
        )
        assert record.attempt_no == 2
        assert second.plaintext != first.plaintext
        assert record.token_hash == hashlib.sha256(
            second.plaintext.encode()
        ).hexdigest()
        with pytest.raises(DashboardReportRenderTokenError):
            DashboardReportRenderTokenService.consume(
                execution_id=running_execution.id,
                plaintext=first.plaintext,
            )
        session = DashboardReportRenderTokenService.consume(
            execution_id=running_execution.id,
            plaintext=second.plaintext,
        )
        assert session["username"] == running_execution.creator

    def test_revoke_blocks_consume(self, running_execution, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "token-retry-secret")
        issued = DashboardReportRenderTokenService.issue(
            running_execution, attempt_no=1
        )
        assert DashboardReportRenderTokenService.revoke_current(
            running_execution
        )
        with pytest.raises(DashboardReportRenderTokenError):
            DashboardReportRenderTokenService.consume(
                execution_id=running_execution.id,
                plaintext=issued.plaintext,
            )


class TestRenderRetryCodes:
    def test_chromium_launch_failed_retries_then_succeeds(
        self, authenticated_user, monkeypatch
    ):
        directory = Directory.objects.create(name="Render Retry", groups=[1])
        dashboard = Dashboard.objects.create(
            name="Render Retry 盘",
            directory=directory,
            groups=[1],
            created_by=authenticated_user.username,
        )
        channel = Channel.objects.create(
            name="Render Retry 通道",
            channel_type="email",
            config={},
            description="测试",
            team=[1],
        )
        subscription = DashboardReportSubscription.objects.create(
            dashboard=dashboard,
            creator=authenticated_user.username,
            name="Render Retry",
            recipient_email="ops@example.com",
            email_channel=channel,
        )
        execution = DashboardReportExecution.objects.create(
            subscription=subscription,
            dashboard=dashboard,
            creator=authenticated_user.username,
        )
        DashboardReportExecutionSnapshot.objects.create(
            execution=execution,
            dashboard_id=dashboard.id,
            creator_id=authenticated_user.username,
            subscription_id=subscription.id,
            subscription_name=subscription.name,
            recipient_email=subscription.recipient_email,
            trigger_type=execution.trigger_type,
            email_channel_id=channel.id,
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
        assert DashboardReportExecutionService.claim_execution(execution.id)
        monkeypatch.setattr(
            "apps.operation_analysis.views.view."
            "DashboardModelViewSet.get_has_permission",
            lambda *args, **kwargs: True,
        )

        outcomes = [
            AttemptResult(
                ok=False,
                failure_stage="render",
                error_code="chromium_launch_failed",
                error_message="launch",
            ),
            AttemptResult(ok=True, side_effect="artifact_created"),
        ]

        def render_side_effect(*args, **kwargs):
            return outcomes.pop(0)

        monkeypatch.setattr(RenderStep, "execute", render_side_effect)
        monkeypatch.setattr(
            "apps.operation_analysis.services.execution_orchestrator."
            "DeliveryStep.execute",
            lambda *args, **kwargs: AttemptResult(
                ok=True, side_effect="delivered"
            ),
        )

        result = ExecutionOrchestrator.execute(execution.id)
        execution.refresh_from_db()
        assert result.status == DashboardReportExecution.Status.SUCCEEDED
        assert execution.attempt_count == 2
        assert execution.failure_stage == ""
