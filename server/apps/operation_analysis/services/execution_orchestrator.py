import logging
from enum import StrEnum

from django.core.exceptions import ValidationError

from apps.base.models import User
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderContractError,
)
from apps.operation_analysis.services.delivery_service import (
    DashboardReportDeliveryError,
    DashboardReportDeliveryService,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.render_snapshot_service import (
    DashboardReportRenderSnapshotService,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)
from apps.operation_analysis.services.resource_state import (
    observe_resource_state,
)
from apps.operation_analysis.services.retry_classifier import (
    MAX_ATTEMPTS,
    RetryClassifier,
)
from apps.operation_analysis.services.retry_types import (
    AttemptResult,
    ClassifierDecisionKind,
    ResumeClass,
)
from apps.operation_analysis.services.execution_timeout_checker import (
    ExecutionTimeoutChecker,
)

logger = logging.getLogger(__name__)


class ExecutionStepResult(StrEnum):
    """兼容旧测试名；成功步请返回 AttemptResult(ok=True)。"""

    COMPLETED = "completed"


class ExecutionStepError(Exception):
    """兼容旧测试；生产 Step 应返回 AttemptResult。"""

    def __init__(self, stage: str, message: str, error_code: str = ""):
        self.stage = stage
        self.message = message
        self.error_code = error_code
        super().__init__(message)

    def to_attempt_result(self) -> AttemptResult:
        return AttemptResult(
            ok=False,
            failure_stage=self.stage,
            error_code=self.error_code or "",
            error_message=self.message,
        )


def _user_team_ids(user: User) -> list[int]:
    team_ids = []
    for item in user.group_list or []:
        raw_id = item.get("id") if isinstance(item, dict) else item
        try:
            team_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return team_ids


def _as_attempt_result(value) -> AttemptResult:
    if isinstance(value, AttemptResult):
        return value
    if value is ExecutionStepResult.COMPLETED or value == (
        ExecutionStepResult.COMPLETED
    ):
        return AttemptResult(ok=True)
    if isinstance(value, DashboardReportExecutionSnapshot):
        return AttemptResult(ok=True)
    if isinstance(value, DashboardReportRenderSnapshot):
        return AttemptResult(ok=True)
    if value is None:
        return AttemptResult(ok=True)
    return AttemptResult(ok=True)


def _resolve_input_snapshot(
    execution: DashboardReportExecution,
    snapshot_out,
) -> DashboardReportExecutionSnapshot:
    if isinstance(snapshot_out, DashboardReportExecutionSnapshot):
        return snapshot_out
    return execution.snapshot


def _resolve_render_snapshot(
    execution: DashboardReportExecution,
    render_out,
) -> DashboardReportRenderSnapshot:
    if isinstance(render_out, DashboardReportRenderSnapshot):
        return render_out
    return execution.render_snapshot


class PermissionStep:
    failure_stage = "permission_check"

    @classmethod
    def _has_render_snapshot(cls, execution: DashboardReportExecution) -> bool:
        try:
            execution.render_snapshot
            return True
        except DashboardReportRenderSnapshot.DoesNotExist:
            return False

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult:
        users = User.objects.filter(
            username=execution.creator,
            domain=execution.creator_domain,
            is_active=True,
        )
        if users.count() != 1:
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="creator_inactive",
                error_message="Execution 创建者无权查看仪表盘",
            )

        # Render Snapshot 冻结后源画布删除：不因存在性再次阻断当前执行
        resource_type = execution.resource_type or "dashboard"
        resource_id = (
            execution.resource_id
            if execution.resource_id is not None
            else execution.dashboard_id
        )
        from apps.operation_analysis.services.canvas_report.permissions import (
            canvas_resource_exists,
            can_view_canvas,
        )

        live_missing = resource_id is None or not canvas_resource_exists(
            resource_type,
            resource_id,
        )
        if live_missing:
            if (
                execution.source_canvas_deleted_during_execution
                and cls._has_render_snapshot(execution)
            ):
                return AttemptResult(ok=True)
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="dashboard_missing",
                error_message="Execution 创建者无权查看仪表盘",
            )

        user = users.get()
        if not user.is_superuser:
            can_view = any(
                can_view_canvas(
                    user,
                    resource_type,
                    resource_id,
                    team_id=team_id,
                )
                for team_id in _user_team_ids(user)
            )
            if not can_view:
                return AttemptResult(
                    ok=False,
                    failure_stage=cls.failure_stage,
                    error_code="dashboard_view_denied",
                    error_message="Execution 创建者无权查看仪表盘",
                )
        return AttemptResult(ok=True)


class SnapshotStep:
    failure_stage = "snapshot"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult | DashboardReportExecutionSnapshot:
        try:
            snapshot = execution.snapshot
        except DashboardReportExecutionSnapshot.DoesNotExist:
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="input_snapshot_absent",
                error_message="Execution Snapshot 不存在",
            )

        if (
            execution.source_canvas_deleted_during_execution
            and execution.resource_id is None
            and execution.dashboard_id is None
        ):
            is_valid = (
                execution.subscription_id is not None
                and snapshot.creator_id == execution.creator
                and snapshot.creator_domain == execution.creator_domain
                and snapshot.subscription_id == execution.subscription_id
                and isinstance(snapshot.filter_values, dict)
            )
        else:
            exec_resource_id = (
                execution.resource_id
                if execution.resource_id is not None
                else execution.dashboard_id
            )
            snap_resource_id = (
                snapshot.resource_id
                if snapshot.resource_id is not None
                else snapshot.dashboard_id
            )
            is_valid = (
                exec_resource_id is not None
                and execution.subscription_id is not None
                and snap_resource_id == exec_resource_id
                and (
                    not snapshot.resource_type
                    or not execution.resource_type
                    or snapshot.resource_type == execution.resource_type
                )
                and snapshot.creator_id == execution.creator
                and snapshot.creator_domain == execution.creator_domain
                and snapshot.subscription_id == execution.subscription_id
                and isinstance(snapshot.filter_values, dict)
            )
        if not is_valid:
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="input_snapshot_corrupt",
                error_message="Execution Snapshot 内容无效",
            )
        return snapshot


class RenderSnapshotStep:
    failure_stage = "render_snapshot"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult | DashboardReportRenderSnapshot:
        try:
            return DashboardReportRenderSnapshotService.create(execution)
        except ValueError as exc:
            logger.exception(
                "创建 Render Snapshot 业务失败: execution_id=%s",
                execution.id,
            )
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="render_snapshot_create_permanent",
                error_message=str(exc) or "Render Snapshot 创建失败",
                side_effect=type(exc).__name__,
            )
        except Exception as exc:
            from django.db import DatabaseError, OperationalError

            transient = isinstance(
                exc,
                (OperationalError, DatabaseError, ConnectionError, TimeoutError),
            )
            logger.exception(
                "创建 Render Snapshot 失败: execution_id=%s transient=%s",
                execution.id,
                transient,
            )
            if transient:
                return AttemptResult(
                    ok=False,
                    failure_stage=cls.failure_stage,
                    error_code="render_snapshot_create_transient",
                    error_message="Render Snapshot 创建失败",
                    side_effect=type(exc).__name__,
                )
            # 未知异常：不 retry
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="",
                error_message="Render Snapshot 创建失败",
                side_effect=type(exc).__name__,
            )


class RenderStep:
    failure_stage = "render"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
        render_snapshot: DashboardReportRenderSnapshot,
    ) -> AttemptResult:
        try:
            DashboardReportRenderService.render(
                execution,
                snapshot,
                render_snapshot,
            )
        except DashboardRenderContractError as exc:
            logger.warning(
                "Dashboard Render Contract 失败: "
                "execution_id=%s widget_id=%s stage=%s code=%s",
                execution.id,
                exc.widget_id,
                getattr(exc, "failure_stage", cls.failure_stage),
                exc.error_code,
            )
            return AttemptResult(
                ok=False,
                failure_stage=getattr(
                    exc, "failure_stage", None
                )
                or cls.failure_stage,
                error_code=exc.error_code
                or "render_contract_business_failed",
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception(
                "Dashboard PDF 渲染失败: execution_id=%s",
                execution.id,
            )
            safe_message = getattr(exc, "safe_message", "报告 PDF 生成失败")
            error_code = getattr(exc, "error_code", "") or ""
            if isinstance(exc, ExecutionStepError):
                safe_message = exc.message
                error_code = exc.error_code or error_code
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code=error_code,
                error_message=safe_message,
            )
        return AttemptResult(ok=True, side_effect="artifact_created")


class DeliveryStep:
    failure_stage = "email"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> AttemptResult:
        try:
            DashboardReportDeliveryService.deliver(execution, snapshot)
        except DashboardReportDeliveryError as exc:
            error_code = exc.error_code or ""
            # 产物不可用时用 render 可重试码，便于 Classifier 走 RENDER
            failure_stage = (
                "render"
                if error_code == "pdf_generate_failed"
                else cls.failure_stage
            )
            return AttemptResult(
                ok=False,
                failure_stage=failure_stage,
                error_code=error_code,
                error_message=str(exc),
            )
        except Exception as exc:
            logger.exception(
                "邮件投递失败: execution_id=%s",
                execution.id,
            )
            return AttemptResult(
                ok=False,
                failure_stage=cls.failure_stage,
                error_code="",
                error_message="邮件投递失败",
                side_effect=type(exc).__name__,
            )
        return AttemptResult(ok=True, side_effect="delivered")


class ExecutionOrchestrator:
    """生产唯一入口：execute(execution_id)。禁止第二生产入口。"""

    @classmethod
    def execute(cls, execution_id: int) -> DashboardReportExecution:
        execution = DashboardReportExecution.objects.select_related(
            "dashboard",
            "subscription",
            "snapshot",
            "render_snapshot",
            "pdf_artifact",
        ).get(pk=execution_id)
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise ValidationError(
                {"status": "Execution 必须先由 Worker 成功领取"}
            )

        resume_class: ResumeClass | None = None
        while True:
            attempt_no = DashboardReportExecutionService.begin_attempt(
                execution
            )
            resource = observe_resource_state(execution)
            if resource.delivery_outcome == "delivered":
                DashboardReportExecutionService.reconcile_delivery_fact(
                    execution,
                    source="orchestrator",
                )
                execution.refresh_from_db()
                if (
                    execution.status
                    == DashboardReportExecution.Status.SUCCEEDED
                ):
                    return execution
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.SUCCEEDED,
                )

            result = cls._run_attempt(
                execution,
                resume_class=resume_class,
            )
            if result.ok:
                # deliver() 可能已按 delivery_outcome 对齐 succeeded
                DashboardReportExecutionService.reconcile_delivery_fact(
                    execution,
                    source="orchestrator",
                )
                execution.refresh_from_db()
                if (
                    execution.status
                    == DashboardReportExecution.Status.SUCCEEDED
                ):
                    return execution
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.SUCCEEDED,
                )

            if result.side_effect:
                logger.info(
                    "Attempt 副作用(仅日志): execution_id=%s "
                    "attempt=%s side_effect=%s",
                    execution.id,
                    attempt_no,
                    result.side_effect,
                )

            resource = observe_resource_state(execution)
            decision = RetryClassifier.classify(
                result,
                attempt_no,
                resource,
            )

            if decision.kind == ClassifierDecisionKind.SUCCEEDED:
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.SUCCEEDED,
                )
            if decision.kind == ClassifierDecisionKind.TERMINAL_UNKNOWN:
                DashboardReportExecutionService.mark_delivery_outcome(
                    execution,
                    DashboardReportExecution.DeliveryOutcome.SMTP_UNKNOWN,
                )
                DashboardReportExecutionService.reconcile_delivery_fact(
                    execution,
                    source="orchestrator",
                )
                execution.refresh_from_db()
                if (
                    execution.status
                    == DashboardReportExecution.Status.UNKNOWN
                ):
                    return execution
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.UNKNOWN,
                    failure_stage=result.failure_stage or "email",
                    error_code=result.error_code or "smtp_result_unknown",
                    error_message=result.error_message,
                )
            if decision.kind == ClassifierDecisionKind.TERMINAL_FAILED:
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.FAILED,
                    failure_stage=result.failure_stage,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )

            # retry：resume_class 唯一来自 Classifier
            resume_class = decision.resume_class
            if resume_class is None or attempt_no >= MAX_ATTEMPTS:
                return DashboardReportExecutionService.transition(
                    execution,
                    DashboardReportExecution.Status.FAILED,
                    failure_stage=result.failure_stage,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
            execution.refresh_from_db()
            if ExecutionTimeoutChecker.is_past_deadline(execution):
                ExecutionTimeoutChecker.converge_one(execution)
                execution.refresh_from_db()
                return execution
            logger.info(
                "Execution 进入下一 attempt: execution_id=%s "
                "attempt=%s resume_class=%s",
                execution.id,
                attempt_no,
                resume_class,
            )

    @classmethod
    def _run_attempt(
        cls,
        execution: DashboardReportExecution,
        *,
        resume_class: ResumeClass | None,
    ) -> AttemptResult:
        try:
            if resume_class is None:
                return cls._run_full(execution)
            if resume_class == ResumeClass.DELIVERY:
                return cls._run_from_delivery(execution)
            if resume_class == ResumeClass.RENDER:
                return cls._run_from_render(execution)
            if resume_class == ResumeClass.RENDER_SNAPSHOT_ENSURE:
                return cls._run_from_render_snapshot(execution)
            return AttemptResult(
                ok=False,
                failure_stage="schedule",
                error_code="unclassified_internal_error",
                error_message=f"未知 resume_class: {resume_class}",
            )
        except ExecutionStepError as exc:
            return exc.to_attempt_result()

    @classmethod
    def _run_full(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult:
        result = _as_attempt_result(PermissionStep.execute(execution))
        if not result.ok:
            return result

        snapshot_out = SnapshotStep.execute(execution)
        result = _as_attempt_result(snapshot_out)
        if not result.ok:
            return result
        snapshot = _resolve_input_snapshot(execution, snapshot_out)

        render_out = RenderSnapshotStep.execute(execution)
        result = _as_attempt_result(render_out)
        if not result.ok:
            return result
        render_snapshot = _resolve_render_snapshot(execution, render_out)

        result = _as_attempt_result(
            RenderStep.execute(execution, snapshot, render_snapshot)
        )
        if not result.ok:
            return result

        return _as_attempt_result(
            DeliveryStep.execute(execution, snapshot)
        )

    @classmethod
    def _run_from_render_snapshot(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult:
        result = _as_attempt_result(PermissionStep.execute(execution))
        if not result.ok:
            return result
        snapshot_out = SnapshotStep.execute(execution)
        result = _as_attempt_result(snapshot_out)
        if not result.ok:
            return result
        snapshot = _resolve_input_snapshot(execution, snapshot_out)
        render_out = RenderSnapshotStep.execute(execution)
        result = _as_attempt_result(render_out)
        if not result.ok:
            return result
        render_snapshot = _resolve_render_snapshot(execution, render_out)
        result = _as_attempt_result(
            RenderStep.execute(execution, snapshot, render_snapshot)
        )
        if not result.ok:
            return result
        return _as_attempt_result(
            DeliveryStep.execute(execution, snapshot)
        )

    @classmethod
    def _run_from_render(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult:
        result = _as_attempt_result(PermissionStep.execute(execution))
        if not result.ok:
            return result
        snapshot_out = SnapshotStep.execute(execution)
        result = _as_attempt_result(snapshot_out)
        if not result.ok:
            return result
        snapshot = _resolve_input_snapshot(execution, snapshot_out)
        try:
            render_snapshot = execution.render_snapshot
        except DashboardReportRenderSnapshot.DoesNotExist:
            return AttemptResult(
                ok=False,
                failure_stage="render_snapshot",
                error_code="render_snapshot_create_transient",
                error_message="Render Snapshot 不存在",
            )
        result = _as_attempt_result(
            RenderStep.execute(execution, snapshot, render_snapshot)
        )
        if not result.ok:
            return result
        return _as_attempt_result(
            DeliveryStep.execute(execution, snapshot)
        )

    @classmethod
    def _run_from_delivery(
        cls,
        execution: DashboardReportExecution,
    ) -> AttemptResult:
        result = _as_attempt_result(PermissionStep.execute(execution))
        if not result.ok:
            return result
        snapshot_out = SnapshotStep.execute(execution)
        result = _as_attempt_result(snapshot_out)
        if not result.ok:
            return result
        snapshot = _resolve_input_snapshot(execution, snapshot_out)
        # resume_class 来自 Classifier；此处只校验 artifact 仍可用
        resource = observe_resource_state(execution)
        if resource.artifact != "valid":
            return AttemptResult(
                ok=False,
                failure_stage="render",
                error_code="pdf_generate_failed",
                error_message="Delivery resume 时 Artifact 不可用",
            )
        return _as_attempt_result(
            DeliveryStep.execute(execution, snapshot)
        )


# 测试辅助：允许注入 AttemptResult 序列以验证 loop（禁止生产调用）
def _testing_run_classifier_loop_with_results(  # pragma: no cover - 测试用
    execution: DashboardReportExecution,
    results: list[AttemptResult],
) -> DashboardReportExecution:
    """仅供测试。生产代码不得调用。"""
    resume_class = None
    idx = 0
    while idx < len(results):
        attempt_no = DashboardReportExecutionService.begin_attempt(execution)
        resource = observe_resource_state(execution)
        if resource.delivery_outcome == "delivered":
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.SUCCEEDED,
            )
        result = results[idx]
        idx += 1
        if result.ok:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.SUCCEEDED,
            )
        resource = observe_resource_state(execution)
        decision = RetryClassifier.classify(result, attempt_no, resource)
        if decision.kind == ClassifierDecisionKind.SUCCEEDED:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.SUCCEEDED,
            )
        if decision.kind == ClassifierDecisionKind.TERMINAL_UNKNOWN:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.UNKNOWN,
                failure_stage=result.failure_stage,
                error_code=result.error_code,
                error_message=result.error_message,
            )
        if decision.kind == ClassifierDecisionKind.TERMINAL_FAILED:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage=result.failure_stage,
                error_code=result.error_code,
                error_message=result.error_message,
            )
        resume_class = decision.resume_class
        if resume_class is None:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage=result.failure_stage,
                error_code=result.error_code,
                error_message=result.error_message,
            )
    return execution
