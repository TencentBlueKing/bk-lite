import logging
from dataclasses import dataclass
from enum import StrEnum

from django.core.exceptions import ValidationError

from apps.base.models import User
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportRenderSnapshot,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.dashboard_report_renderer import (
    DashboardRenderContractError,
)
from apps.operation_analysis.services.render_snapshot_service import (
    DashboardReportRenderSnapshotService,
)
from apps.operation_analysis.services.delivery_service import (
    DashboardReportDeliveryError,
    DashboardReportDeliveryService,
)
from apps.operation_analysis.services.report_render_service import (
    DashboardReportRenderService,
)

logger = logging.getLogger(__name__)


class ExecutionStepResult(StrEnum):
    COMPLETED = "completed"


@dataclass
class ExecutionStepError(Exception):
    stage: str
    message: str


def _user_team_ids(user: User) -> list[int]:
    team_ids = []
    for item in user.group_list or []:
        raw_id = item.get("id") if isinstance(item, dict) else item
        try:
            team_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    return team_ids


class PermissionStep:
    failure_stage = "permission_check"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> ExecutionStepResult:
        users = User.objects.filter(
            username=execution.creator,
            is_active=True,
        )
        if users.count() != 1 or execution.dashboard is None:
            raise ExecutionStepError(
                cls.failure_stage,
                "Execution 创建者无权查看仪表盘",
            )

        user = users.get()
        if not user.is_superuser:
            from apps.operation_analysis.views.view import DashboardModelViewSet

            viewset = DashboardModelViewSet()
            can_view = any(
                viewset.get_has_permission(
                    user,
                    execution.dashboard,
                    team_id,
                    is_check=True,
                )
                for team_id in _user_team_ids(user)
            )
            if not can_view:
                raise ExecutionStepError(
                    cls.failure_stage,
                    "Execution 创建者无权查看仪表盘",
                )
        return ExecutionStepResult.COMPLETED


class SnapshotStep:
    failure_stage = "snapshot"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> DashboardReportExecutionSnapshot:
        try:
            snapshot = execution.snapshot
        except DashboardReportExecutionSnapshot.DoesNotExist as exc:
            raise ExecutionStepError(
                cls.failure_stage,
                "Execution Snapshot 不存在",
            ) from exc

        is_valid = (
            execution.dashboard_id is not None
            and execution.subscription_id is not None
            and snapshot.dashboard_id == execution.dashboard_id
            and snapshot.creator_id == execution.creator
            and snapshot.subscription_id == execution.subscription_id
            and isinstance(snapshot.filter_values, dict)
        )
        if not is_valid:
            raise ExecutionStepError(
                cls.failure_stage,
                "Execution Snapshot 内容无效",
            )
        return snapshot


class RenderSnapshotStep:
    failure_stage = "snapshot"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
    ) -> DashboardReportRenderSnapshot:
        try:
            return DashboardReportRenderSnapshotService.create(execution)
        except Exception as exc:
            logger.exception(
                "创建 Render Snapshot 失败: execution_id=%s",
                execution.id,
            )
            raise ExecutionStepError(
                cls.failure_stage,
                "Render Snapshot 创建失败",
            ) from exc


class RenderStep:
    failure_stage = "render"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
        render_snapshot: DashboardReportRenderSnapshot,
    ) -> ExecutionStepResult:
        try:
            DashboardReportRenderService.render(
                execution,
                snapshot,
                render_snapshot,
            )
        except DashboardRenderContractError as exc:
            logger.warning(
                "Dashboard Render Contract 失败: "
                "execution_id=%s widget_id=%s",
                execution.id,
                exc.widget_id,
            )
            raise ExecutionStepError(
                cls.failure_stage,
                str(exc),
            ) from exc
        except Exception as exc:
            logger.exception(
                "Dashboard PDF 渲染失败: execution_id=%s",
                execution.id,
            )
            safe_message = getattr(exc, "safe_message", "报告 PDF 生成失败")
            if isinstance(exc, ExecutionStepError):
                safe_message = exc.message
            raise ExecutionStepError(
                cls.failure_stage,
                safe_message,
            ) from exc
        return ExecutionStepResult.COMPLETED


class DeliveryStep:
    failure_stage = "email"

    @classmethod
    def execute(
        cls,
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> ExecutionStepResult:
        try:
            DashboardReportDeliveryService.deliver(execution, snapshot)
        except DashboardReportDeliveryError as exc:
            raise ExecutionStepError(
                cls.failure_stage,
                str(exc),
            ) from exc
        except Exception as exc:
            logger.exception(
                "邮件投递失败: execution_id=%s",
                execution.id,
            )
            raise ExecutionStepError(
                cls.failure_stage,
                "邮件投递失败",
            ) from exc
        return ExecutionStepResult.COMPLETED


class ExecutionOrchestrator:
    @classmethod
    def execute(cls, execution_id: int) -> DashboardReportExecution:
        execution = DashboardReportExecution.objects.select_related(
            "dashboard",
            "subscription",
            "snapshot",
        ).get(pk=execution_id)
        if execution.status != DashboardReportExecution.Status.RUNNING:
            raise ValidationError(
                {"status": "Execution 必须先由 Worker 成功领取"}
            )

        try:
            PermissionStep.execute(execution)
            snapshot = SnapshotStep.execute(execution)
            render_snapshot = RenderSnapshotStep.execute(execution)
            RenderStep.execute(
                execution,
                snapshot,
                render_snapshot,
            )
            DeliveryStep.execute(execution, snapshot)
        except ExecutionStepError as exc:
            return DashboardReportExecutionService.transition(
                execution,
                DashboardReportExecution.Status.FAILED,
                failure_stage=exc.stage,
                error_message=exc.message,
            )

        return DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.SUCCEEDED,
        )
