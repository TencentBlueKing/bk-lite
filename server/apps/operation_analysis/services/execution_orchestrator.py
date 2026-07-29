from dataclasses import dataclass
from enum import StrEnum

from apps.base.models import User
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)


class ExecutionStepResult(StrEnum):
    COMPLETED = "completed"
    PLACEHOLDER = "placeholder"


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


class RenderStep:
    @staticmethod
    def execute(
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> ExecutionStepResult:
        return ExecutionStepResult.PLACEHOLDER


class DeliveryStep:
    @staticmethod
    def execute(
        execution: DashboardReportExecution,
        snapshot: DashboardReportExecutionSnapshot,
    ) -> ExecutionStepResult:
        return ExecutionStepResult.PLACEHOLDER


class ExecutionOrchestrator:
    @classmethod
    def execute(cls, execution_id: int) -> DashboardReportExecution:
        execution = DashboardReportExecution.objects.select_related(
            "dashboard",
            "subscription",
            "snapshot",
        ).get(pk=execution_id)
        DashboardReportExecutionService.transition(
            execution,
            DashboardReportExecution.Status.RUNNING,
        )

        try:
            PermissionStep.execute(execution)
            snapshot = SnapshotStep.execute(execution)
            RenderStep.execute(execution, snapshot)
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
