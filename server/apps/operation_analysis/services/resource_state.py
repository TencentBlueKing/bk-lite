from __future__ import annotations

from django.utils import timezone

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportRenderSnapshot,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.operation_analysis.services.retry_types import ResourceState


def _resolve_resource_id(
    *,
    resource_id: int | None,
    dashboard_id: int | None,
) -> int | None:
    if resource_id is not None:
        return resource_id
    return dashboard_id


def _input_snapshot_state(
    execution: DashboardReportExecution,
) -> str:
    try:
        snapshot = execution.snapshot
    except DashboardReportExecutionSnapshot.DoesNotExist:
        return "absent"

    exec_resource_id = _resolve_resource_id(
        resource_id=execution.resource_id,
        dashboard_id=execution.dashboard_id,
    )
    snap_resource_id = _resolve_resource_id(
        resource_id=snapshot.resource_id,
        dashboard_id=snapshot.dashboard_id,
    )
    is_valid = (
        exec_resource_id is not None
        and snap_resource_id == exec_resource_id
        and execution.subscription_id is not None
        and snapshot.creator_id == execution.creator
        and snapshot.creator_domain == execution.creator_domain
        and snapshot.subscription_id == execution.subscription_id
        and isinstance(snapshot.filter_values, dict)
    )
    return "valid" if is_valid else "corrupt"


def _render_snapshot_state(
    execution: DashboardReportExecution,
) -> str:
    try:
        render_snapshot = execution.render_snapshot
    except DashboardReportRenderSnapshot.DoesNotExist:
        return "absent"
    if render_snapshot.execution_id != execution.id:
        return "corrupt"
    exec_resource_id = _resolve_resource_id(
        resource_id=execution.resource_id,
        dashboard_id=execution.dashboard_id,
    )
    snap_resource_id = _resolve_resource_id(
        resource_id=render_snapshot.resource_id,
        dashboard_id=render_snapshot.dashboard_id,
    )
    if (
        exec_resource_id is not None
        and snap_resource_id is not None
        and snap_resource_id != exec_resource_id
    ):
        return "corrupt"
    if (
        execution.dashboard_id is not None
        and render_snapshot.dashboard_id is not None
        and render_snapshot.dashboard_id != execution.dashboard_id
    ):
        return "corrupt"
    return "valid"


def _artifact_state(execution: DashboardReportExecution) -> str:
    try:
        artifact = execution.pdf_artifact
    except DashboardReportPdfArtifact.DoesNotExist:
        return "absent"
    if artifact.expires_at <= timezone.now():
        return "unusable"
    try:
        DashboardReportRenderService.resolve_artifact_path(artifact)
    except Exception:
        return "unusable"
    return "valid"


def _delivery_outcome(execution: DashboardReportExecution) -> str:
    """只读 durable 投递事实；不回退到 error_code / status。"""
    outcome = getattr(
        execution,
        "delivery_outcome",
        DashboardReportExecution.DeliveryOutcome.NOT_DELIVERED,
    )
    if outcome == DashboardReportExecution.DeliveryOutcome.DELIVERED:
        return "delivered"
    if outcome == DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN:
        return "smtp_unknown"
    # 兼容历史行：仅有 delivered_at、尚未回填 delivery_outcome
    if execution.delivered_at is not None:
        return "delivered"
    return "not_delivered"


def observe_resource_state(
    execution: DashboardReportExecution,
) -> ResourceState:
    """由 Orchestrator 调用；Step 不得构造此对象作为 Classifier 输入。"""
    return ResourceState(
        input_snapshot=_input_snapshot_state(execution),
        render_snapshot=_render_snapshot_state(execution),
        artifact=_artifact_state(execution),
        delivery_outcome=_delivery_outcome(execution),
    )
