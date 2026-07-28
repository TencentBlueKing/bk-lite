from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
)


class DashboardReportExecutionService:
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
        execution.transition_to(DashboardReportExecution.Status.RUNNING)
        execution.transition_to(DashboardReportExecution.Status.SUCCEEDED)
        return execution
