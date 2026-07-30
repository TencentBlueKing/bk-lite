import hashlib
from datetime import timedelta
from pathlib import Path

import fitz
import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderError,
    DashboardRenderContractError,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.operation_analysis.tasks.tasks import render_dashboard_report_task
from apps.system_mgmt.models import Channel
from apps.system_mgmt.models import User as SystemUser


pytestmark = pytest.mark.django_db


def write_valid_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "BK-Lite dashboard report")
    document.save(path)
    document.close()
    with path.open("ab") as file_handle:
        file_handle.write(b"\0" * 10_000)


def _allow_dashboard_view(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.operation_analysis.views.view."
        "DashboardModelViewSet.get_has_permission",
        lambda self, user, dashboard, team_id, **kwargs: True,
    )


@pytest.fixture
def email_channel():
    return Channel.objects.create(
        name="渲染邮件通道",
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
def pending_execution(authenticated_user, email_channel):
    SystemUser.objects.create(
        username=authenticated_user.username,
        display_name=authenticated_user.username,
        email="testuser@example.com",
        password="unused",
        domain=authenticated_user.domain,
        group_list=authenticated_user.group_list,
    )
    directory = Directory.objects.create(name="渲染测试目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="渲染测试仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
        view_sets=[
            {
                "i": "chart-1",
                "itemType": "widget",
                "valueConfig": {
                    "chartType": "line",
                    "dataSource": 17,
                },
            }
        ],
        filters=[{"id": "environment", "type": "selector"}],
        other={"title": "运营总览"},
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="日报",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        config={"filter_values": {"environment": "production"}},
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
        email_channel_id=subscription.email_channel_id,
        filter_values={"environment": "production"},
    )
    return execution


def test_render_task_claims_execution_and_records_pdf_artifact(
    pending_execution,
    authenticated_user,
    monkeypatch,
    tmp_path,
):
    _allow_dashboard_view(monkeypatch)
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))

    def render_pdf(self, request):
        assert request.execution_id == pending_execution.id
        assert (
            request.render_url
            == f"http://web.test/ops-analysis/render/execution/{pending_execution.id}"
        )
        assert request.render_token
        write_valid_pdf(request.output_path)

    monkeypatch.setenv("DASHBOARD_REPORT_WEB_BASE_URL", "http://web.test")
    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_report_renderer."
        "DashboardChromiumRenderer.render",
        render_pdf,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.delivery_service.Channel.decrypt_field",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "apps.system_mgmt.utils.channel_utils.send_email_to_user",
        lambda *args, **kwargs: {"result": True, "message": "ok"},
    )

    result = render_dashboard_report_task(pending_execution.id)

    pending_execution.refresh_from_db()
    artifact = DashboardReportPdfArtifact.objects.get(
        execution=pending_execution
    )
    assert result == {
        "claimed": True,
        "execution_id": pending_execution.id,
        "status": "succeeded",
        "rendered": True,
    }
    assert pending_execution.status == DashboardReportExecution.Status.SUCCEEDED
    assert pending_execution.finished_at is not None
    assert artifact.storage_reference == (
        f"execution-{pending_execution.id}/report.pdf"
    )
    assert artifact.filename.startswith("渲染测试仪表盘_")
    assert artifact.filename.endswith(".pdf")
    assert artifact.expires_at > artifact.created_at
    assert artifact.size_bytes > 0
    assert len(artifact.sha256) == 64
    assert DashboardReportRenderService.resolve_artifact_path(
        artifact
    ).read_bytes()
    artifact_path = tmp_path / artifact.storage_reference
    assert artifact_path.is_file()
    assert artifact.sha256 == hashlib.sha256(
        artifact_path.read_bytes()
    ).hexdigest()
    with fitz.open(artifact_path) as document:
        assert document.page_count == 1
    system_user = SystemUser.objects.get(
        username=authenticated_user.username
    )
    assert system_user.last_login is None


def test_expired_pdf_artifact_cannot_be_read_for_delivery(
    pending_execution,
    monkeypatch,
    tmp_path,
):
    pending_execution.status = DashboardReportExecution.Status.RUNNING
    pending_execution.save(update_fields=["status"])
    artifact = DashboardReportPdfArtifact.objects.create(
        execution=pending_execution,
        storage_reference="execution-expired/report.pdf",
        filename="expired.pdf",
        size_bytes=2048,
        sha256="a" * 64,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    monkeypatch.setenv(
        "DASHBOARD_REPORT_ARTIFACT_ROOT",
        str(tmp_path),
    )

    with pytest.raises(DashboardRenderError, match="已过期"):
        DashboardReportRenderService.resolve_artifact_path(artifact)


def test_render_contract_failure_blocks_pdf_and_fails_execution(
    pending_execution,
    monkeypatch,
    tmp_path,
):
    _allow_dashboard_view(monkeypatch)
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_REPORT_WEB_BASE_URL", "http://web.test")

    def fail_render(self, request):
        raise DashboardRenderContractError(
            widget_id="chart-1"
        )

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_report_renderer."
        "DashboardChromiumRenderer.render",
        fail_render,
    )

    result = render_dashboard_report_task(pending_execution.id)

    pending_execution.refresh_from_db()
    assert result["status"] == "failed"
    assert pending_execution.status == DashboardReportExecution.Status.FAILED
    assert pending_execution.failure_stage == "render"
    assert pending_execution.error_message == (
        "Dashboard 渲染失败: widget=chart-1"
    )
    assert not DashboardReportPdfArtifact.objects.filter(
        execution=pending_execution
    ).exists()
    assert list(tmp_path.glob("*.pdf")) == []


def test_pdf_generation_failure_marks_render_failed(
    pending_execution,
    monkeypatch,
    tmp_path,
):
    _allow_dashboard_view(monkeypatch)
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_REPORT_WEB_BASE_URL", "http://web.test")

    def fail_pdf(self, request):
        raise RuntimeError("Chromium PDF generation failed")

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_report_renderer."
        "DashboardChromiumRenderer.render",
        fail_pdf,
    )

    render_dashboard_report_task(pending_execution.id)

    pending_execution.refresh_from_db()
    assert pending_execution.status == DashboardReportExecution.Status.FAILED
    assert pending_execution.failure_stage == "render"
    assert pending_execution.error_message == "报告 PDF 生成失败"
    assert not DashboardReportPdfArtifact.objects.filter(
        execution=pending_execution
    ).exists()


def test_execution_cannot_render_twice(
    pending_execution,
    monkeypatch,
    tmp_path,
):
    _allow_dashboard_view(monkeypatch)
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_REPORT_WEB_BASE_URL", "http://web.test")
    render_calls = []

    def render_pdf(self, request):
        render_calls.append(request.execution_id)
        write_valid_pdf(request.output_path)

    monkeypatch.setattr(
        "apps.operation_analysis.services.dashboard_report_renderer."
        "DashboardChromiumRenderer.render",
        render_pdf,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.delivery_service.Channel.decrypt_field",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "apps.system_mgmt.utils.channel_utils.send_email_to_user",
        lambda *args, **kwargs: {"result": True, "message": "ok"},
    )

    first = render_dashboard_report_task(pending_execution.id)
    second = render_dashboard_report_task(pending_execution.id)

    assert first["claimed"] is True
    assert second == {
        "claimed": False,
        "execution_id": pending_execution.id,
    }
    assert render_calls == [pending_execution.id]
    assert DashboardReportPdfArtifact.objects.filter(
        execution=pending_execution
    ).count() == 1


def test_render_task_does_not_claim_non_pending_execution(
    pending_execution,
):
    assert DashboardReportExecutionService.claim_execution(
        pending_execution.id
    )

    result = render_dashboard_report_task(pending_execution.id)

    assert result == {
        "claimed": False,
        "execution_id": pending_execution.id,
    }


def test_render_task_uses_dedicated_queue():
    assert render_dashboard_report_task.queue == "dashboard_report_render"
