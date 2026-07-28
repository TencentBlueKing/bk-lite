import logging
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
)

logger = logging.getLogger(__name__)


class DashboardReportExecutionService:
    SNAPSHOT_FAILURE_MESSAGE = "Execution Input Snapshot 创建失败"

    @staticmethod
    def _snapshot_filter_values(
        subscription: DashboardReportSubscription,
    ) -> dict:
        filter_values = (subscription.config or {}).get("filter_values", {})
        if not isinstance(filter_values, dict):
            raise ValidationError("filter_values 必须是对象")
        return deepcopy(filter_values)

    @classmethod
    def _create_snapshot(
        cls,
        execution: DashboardReportExecution,
        subscription: DashboardReportSubscription,
    ) -> DashboardReportExecutionSnapshot:
        return DashboardReportExecutionSnapshot.objects.create(
            execution=execution,
            dashboard_id=subscription.dashboard_id,
            creator_id=subscription.creator,
            subscription_id=subscription.id,
            filter_values=cls._snapshot_filter_values(subscription),
        )

    @classmethod
    @transaction.atomic
    def execute_manual(
        cls,
        request,
        subscription: DashboardReportSubscription,
    ) -> DashboardReportExecution:
        if subscription.creator != request.user.username:
            raise PermissionDenied("只能执行自己的报告订阅")
        if subscription.dashboard is None:
            raise PermissionDenied("源仪表盘已不存在，不能执行该订阅")

        DashboardSubscriptionService.require_dashboard_view(
            request,
            subscription.dashboard,
        )
        execution = DashboardReportExecution.objects.create(
            subscription=subscription,
            dashboard=subscription.dashboard,
            creator=subscription.creator,
            trigger_type=DashboardReportExecution.TriggerType.MANUAL,
        )
        try:
            with transaction.atomic():
                cls._create_snapshot(execution, subscription)
        except Exception:
            logger.exception(
                "创建 Execution Input Snapshot 失败: execution_id=%s",
                execution.id,
            )
            execution.transition_to(DashboardReportExecution.Status.RUNNING)
            execution.transition_to(
                DashboardReportExecution.Status.FAILED,
                failure_stage="snapshot",
                error_message=cls.SNAPSHOT_FAILURE_MESSAGE,
            )
        return execution
