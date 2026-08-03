"""A8 Execution / Snapshot 180 天清理（D4 安全谓词）。"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import Dashboard, Directory
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportRenderSnapshot,
    DashboardReportRenderToken,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.execution_retention_cleanup_service import (
    ExecutionRetentionCleanupService,
    execution_retention_days,
)
from apps.system_mgmt.models import Channel


pytestmark = pytest.mark.django_db


@pytest.fixture
def email_channel(db):
    return Channel.objects.create(
        name="保留清理通道",
        channel_type="email",
        config={},
        description="测试",
        team=[1],
    )


@pytest.fixture
def subscription(authenticated_user, email_channel):
    directory = Directory.objects.create(name="保留目录", groups=[1])
    dashboard = Dashboard.objects.create(
        name="保留仪表盘",
        directory=directory,
        groups=[1],
        created_by=authenticated_user.username,
    )
    return DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator=authenticated_user.username,
        name="保留订阅",
        recipient_email="ops@example.com",
        email_channel=email_channel,
        deleted_at=None,
        deleted_by="",
    )


def _make_execution(
    subscription,
    *,
    status,
    finished_at=None,
    created_at=None,
):
    execution = DashboardReportExecution.objects.create(
        subscription=subscription,
        dashboard=subscription.dashboard,
        creator=subscription.creator,
        status=status,
        finished_at=finished_at,
    )
    if created_at is not None:
        DashboardReportExecution.objects.filter(pk=execution.pk).update(
            created_at=created_at
        )
        execution.refresh_from_db()
    return execution


def _attach_related(execution, tmp_path=None):
    DashboardReportExecutionSnapshot.objects.create(
        execution=execution,
        dashboard_id=execution.dashboard_id or 0,
        creator_id=execution.creator,
        subscription_id=execution.subscription_id or 0,
        subscription_name="保留订阅",
        recipient_email="ops@example.com",
        trigger_type=execution.trigger_type,
    )
    DashboardReportRenderSnapshot.objects.create(
        execution=execution,
        dashboard_id=execution.dashboard_id or 0,
        dashboard_name="保留仪表盘",
        dashboard_updated_at=timezone.now(),
        view_sets=[],
        filters=[],
        other={},
        widget_manifest=[],
    )
    DashboardReportRenderToken.objects.create(
        execution=execution,
        token_hash=f"hash-{execution.id}",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    if tmp_path is not None:
        storage_reference = f"execution-{execution.id}/report.pdf"
        path = tmp_path / storage_reference
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF")
        DashboardReportPdfArtifact.objects.create(
            execution=execution,
            storage_reference=storage_reference,
            filename="report.pdf",
            size_bytes=4,
            sha256="b" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )


def test_execution_retention_days_default():
    assert execution_retention_days() == 180


def test_deletes_succeeded_execution_older_than_181_days(
    subscription, tmp_path, monkeypatch
):
    monkeypatch.setenv("DASHBOARD_REPORT_ARTIFACT_ROOT", str(tmp_path))
    now = timezone.now()
    old = now - timedelta(days=181)
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.SUCCEEDED,
        finished_at=old,
        created_at=old,
    )
    _attach_related(execution, tmp_path=tmp_path)
    sub_id = subscription.id

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.scanned == 1
    assert stats.deleted == 1
    assert not DashboardReportExecution.objects.filter(pk=execution.pk).exists()
    assert not DashboardReportExecutionSnapshot.objects.filter(
        execution_id=execution.id
    ).exists()
    assert not DashboardReportRenderSnapshot.objects.filter(
        execution_id=execution.id
    ).exists()
    assert not DashboardReportRenderToken.objects.filter(
        execution_id=execution.id
    ).exists()
    assert not DashboardReportPdfArtifact.objects.filter(
        execution_id=execution.id
    ).exists()
    assert not (tmp_path / f"execution-{execution.id}").exists()

    subscription.refresh_from_db()
    assert subscription.id == sub_id
    assert subscription.deleted_at is None


def test_deletes_failed_and_unknown_by_finished_at(subscription):
    now = timezone.now()
    failed = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.FAILED,
        finished_at=now - timedelta(days=200),
    )
    unknown = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.UNKNOWN,
        finished_at=now - timedelta(days=200),
    )
    _attach_related(failed)
    _attach_related(unknown)

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.deleted == 2
    assert not DashboardReportExecution.objects.filter(
        pk__in=[failed.pk, unknown.pk]
    ).exists()


def test_falls_back_to_created_at_when_finished_at_null(subscription):
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.FAILED,
        finished_at=None,
        created_at=now - timedelta(days=200),
    )

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.deleted == 1
    assert not DashboardReportExecution.objects.filter(pk=execution.pk).exists()


def test_pending_is_not_deleted(subscription):
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.PENDING,
        created_at=now - timedelta(days=400),
    )

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.scanned == 0
    assert DashboardReportExecution.objects.filter(pk=execution.pk).exists()


def test_running_is_not_deleted(subscription):
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.RUNNING,
        created_at=now - timedelta(days=400),
    )

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.scanned == 0
    assert DashboardReportExecution.objects.filter(pk=execution.pk).exists()


def test_recent_terminal_execution_is_kept(subscription):
    now = timezone.now()
    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.SUCCEEDED,
        finished_at=now - timedelta(days=10),
    )

    stats = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180
    )
    assert stats.scanned == 0
    assert DashboardReportExecution.objects.filter(pk=execution.pk).exists()


def test_subscription_lifecycle_fields_preserved(subscription):
    now = timezone.now()
    subscription.deleted_at = now - timedelta(days=1)
    subscription.deleted_by = "auditor"
    subscription.terminated_at = now - timedelta(days=2)
    subscription.terminated_by = "system"
    subscription.termination_reason = "dashboard_deleted"
    subscription.save()

    execution = _make_execution(
        subscription,
        status=DashboardReportExecution.Status.SUCCEEDED,
        finished_at=now - timedelta(days=200),
    )

    ExecutionRetentionCleanupService.cleanup(now=now, retention_days=180)
    assert not DashboardReportExecution.objects.filter(pk=execution.pk).exists()

    preserved = DashboardReportSubscription.all_objects.get(pk=subscription.pk)
    assert preserved.deleted_at is not None
    assert preserved.deleted_by == "auditor"
    assert preserved.terminated_at is not None
    assert preserved.terminated_by == "system"
    assert preserved.termination_reason == "dashboard_deleted"


def test_batch_limit_deletes_in_chunks(subscription):
    now = timezone.now()
    old = now - timedelta(days=200)
    ids = []
    for _ in range(5):
        execution = _make_execution(
            subscription,
            status=DashboardReportExecution.Status.SUCCEEDED,
            finished_at=old,
            created_at=old,
        )
        ids.append(execution.id)

    first = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180, limit=2
    )
    assert first.scanned == 2
    assert first.deleted == 2
    assert DashboardReportExecution.objects.filter(pk__in=ids).count() == 3

    second = ExecutionRetentionCleanupService.cleanup(
        now=now, retention_days=180, limit=10
    )
    assert second.deleted == 3
    assert DashboardReportExecution.objects.filter(pk__in=ids).count() == 0


def test_beat_registers_execution_retention_cleanup_task():
    from apps.operation_analysis.config import CELERY_BEAT_SCHEDULE

    entry = CELERY_BEAT_SCHEDULE["cleanup_expired_dashboard_report_executions"]
    assert (
        entry["task"]
        == "operation_analysis.cleanup_expired_dashboard_report_executions"
    )
