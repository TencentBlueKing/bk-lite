"""A7 PDF artifact cleanup（D4 安全谓词）。"""

from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportPdfArtifact,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.pdf_artifact_cleanup_service import (
    PdfArtifactCleanupService,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="清理邮件通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription(authenticated_user, email_channel):
    directory = Directory.objects.create(name="清理目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="清理仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="清理订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
    )


def _make_execution(subscription, *, status, finished_at=None):
    return DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=subscription.creator,
        status=status,
        finished_at=finished_at,
    )


def _make_artifact(
    execution,
    *,
    expires_at,
    root: Path,
    write_file: bool = True,
):
    storage_reference = f"execution-{execution.id}/report.pdf"
    path = root / storage_reference
    if write_file:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 cleanup-test")
    return DashboardReportPdfArtifact.objects.create(
        execution=execution,
        storage_reference=storage_reference,
        filename="report.pdf",
        size_bytes=20,
        sha256="a" * 64,
        expires_at=expires_at,
    )


def test_expired_succeeded_artifact_is_deleted(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.SUCCEEDED,
        finished_at=now - timedelta(hours=2),
    )
    artifact = _make_artifact(
        execution,
        expires_at=now - timedelta(minutes=1),
        root=tmp_path,
    )
    path = tmp_path / artifact.storage_reference
    assert path.is_file()

    stats = PdfArtifactCleanupService.cleanup(now=now)
    assert stats.scanned == 1
    assert stats.deleted == 1
    assert not DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).exists()
    assert not path.exists()


def test_unexpired_artifact_is_kept(subscription, tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.SUCCEEDED,
        finished_at=now,
    )
    artifact = _make_artifact(
        execution,
        expires_at=now + timedelta(hours=1),
        root=tmp_path,
    )

    stats = PdfArtifactCleanupService.cleanup(now=now)
    assert stats.scanned == 0
    assert stats.deleted == 0
    assert DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).exists()
    assert (tmp_path / artifact.storage_reference).is_file()


def test_running_expired_artifact_is_not_deleted(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.RUNNING,
    )
    artifact = _make_artifact(
        execution,
        expires_at=now - timedelta(hours=1),
        root=tmp_path,
    )

    stats = PdfArtifactCleanupService.cleanup(now=now)
    assert stats.scanned == 0
    assert DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).exists()
    assert (tmp_path / artifact.storage_reference).is_file()


def test_pending_expired_artifact_is_not_deleted(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.PENDING,
    )
    artifact = _make_artifact(
        execution,
        expires_at=now - timedelta(hours=1),
        root=tmp_path,
    )

    stats = PdfArtifactCleanupService.cleanup(now=now)
    assert stats.scanned == 0
    assert DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).exists()


def test_cleanup_is_idempotent_when_repeated(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.FAILED,
        finished_at=now - timedelta(hours=1),
    )
    _make_artifact(
        execution,
        expires_at=now - timedelta(minutes=5),
        root=tmp_path,
    )

    first = PdfArtifactCleanupService.cleanup(now=now)
    second = PdfArtifactCleanupService.cleanup(now=now)
    assert first.deleted == 1
    assert second.scanned == 0
    assert second.deleted == 0
    assert DashboardReportPdfArtifact.objects.count() == 0


def test_missing_file_cleanup_is_idempotent(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.UNKNOWN,
        finished_at=now - timedelta(hours=1),
    )
    artifact = _make_artifact(
        execution,
        expires_at=now - timedelta(minutes=1),
        root=tmp_path,
        write_file=False,
    )
    assert not (tmp_path / artifact.storage_reference).exists()

    stats = PdfArtifactCleanupService.cleanup(now=now)
    assert stats.deleted == 1
    assert stats.file_missing == 1
    assert not DashboardReportPdfArtifact.objects.filter(pk=artifact.pk).exists()

    again = PdfArtifactCleanupService.cleanup(now=now)
    assert again.scanned == 0


def test_beat_registers_pdf_artifact_cleanup_task():
    from apps.operation_analysis.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE[
        "cleanup_expired_dashboard_report_pdf_artifacts"
    ]
    assert (
        entry["task"]
        == "operation_analysis.cleanup_expired_dashboard_report_pdf_artifacts"
    )
