# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/7/14 16:34
# @Author: windyzhao
from celery import shared_task

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.services.execution_orchestrator import (
    ExecutionOrchestrator,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
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
