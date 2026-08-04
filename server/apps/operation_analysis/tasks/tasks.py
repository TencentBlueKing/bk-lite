# -- coding: utf-8 --
from celery import shared_task

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.services.due_subscription_scanner import (
    DueSubscriptionScanner,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
)
from apps.operation_analysis.services.execution_retention_cleanup_service import (
    ExecutionRetentionCleanupService,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.execution_timeout_checker import (
    ExecutionTimeoutChecker,
)
from apps.operation_analysis.services.pdf_artifact_cleanup_service import (
    PdfArtifactCleanupService,
)


@shared_task(
    name="operation_analysis.render_dashboard_report",
    queue="dashboard_report_render",
    max_retries=0,
)
def render_dashboard_report_task(execution_id: int) -> dict:
    if not DashboardReportExecutionService.claim_execution(execution_id):
        return {
            "claimed": False,
            "execution_id": execution_id,
        }

    execution = ExecutionOrchestrator.execute(execution_id)
    rendered = DashboardReportExecution.objects.filter(
        pk=execution_id,
        pdf_artifact__isnull=False,
    ).exists()
    return {
        "claimed": True,
        "execution_id": execution_id,
        "status": execution.status,
        "rendered": rendered,
    }


@shared_task(
    name="operation_analysis.scan_due_dashboard_report_subscriptions",
    max_retries=0,
)
def scan_due_dashboard_report_subscriptions_task() -> dict:
    """扫描到期订阅并创建 scheduled Execution；不执行 Render/Delivery。"""
    stats = DueSubscriptionScanner.scan()
    return {
        "scanned": stats.scanned,
        "created": stats.created,
        "skipped_in_flight": stats.skipped_in_flight,
        "already_exists": stats.already_exists,
        "skipped_other": stats.skipped_other,
    }


@shared_task(
    name="operation_analysis.converge_timed_out_dashboard_report_executions",
    max_retries=0,
)
def converge_timed_out_dashboard_report_executions_task() -> dict:
    """收敛超时/orphan running Execution；不重 claim、不重发。"""
    stats = ExecutionTimeoutChecker.sweep()
    return {
        "scanned": stats.scanned,
        "failed": stats.failed,
        "succeeded": stats.succeeded,
        "unknown": stats.unknown,
        "skipped": stats.skipped,
    }


@shared_task(
    name="operation_analysis.cleanup_expired_dashboard_report_pdf_artifacts",
    max_retries=0,
)
def cleanup_expired_dashboard_report_pdf_artifacts_task() -> dict:
    """清理已过期且所属 Execution 已终态的 PDF artifact（A7）。"""
    stats = PdfArtifactCleanupService.cleanup()
    return {
        "scanned": stats.scanned,
        "deleted": stats.deleted,
        "file_missing": stats.file_missing,
        "errors": stats.errors,
    }


@shared_task(
    name="operation_analysis.cleanup_expired_dashboard_report_executions",
    max_retries=0,
)
def cleanup_expired_dashboard_report_executions_task() -> dict:
    """分批清理超过保留期的终态 Execution 及级联 Snapshot（A8）。"""
    stats = ExecutionRetentionCleanupService.cleanup()
    return {
        "scanned": stats.scanned,
        "deleted": stats.deleted,
        "errors": stats.errors,
        "retention_days": stats.retention_days,
    }
