from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)
from apps.operation_analysis.serializers.subscription_serializers import (
    DashboardReportSubscriptionSerializer,
)
from apps.operation_analysis.services.execution_service import (
    DashboardReportExecutionService,
)
from apps.operation_analysis.services.subscription_service import (
    DashboardSubscriptionService,
)


class DashboardReportSubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = DashboardReportSubscriptionSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = DashboardReportSubscription.objects.select_related(
            "dashboard"
        )
        user = self.request.user
        if not getattr(user, "is_superuser", False):
            queryset = queryset.filter(creator=user.username)
        dashboard_id = self.request.query_params.get("dashboard_id")
        if dashboard_id:
            queryset = queryset.filter(dashboard_id=dashboard_id)
        return queryset.order_by("-id")

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("view-View")
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        DashboardSubscriptionService.create(self.request, serializer)

    def perform_update(self, serializer):
        DashboardSubscriptionService.update(
            self.request,
            self.get_object(),
            serializer,
        )

    @HasPermission("view-View")
    @action(detail=True, methods=["post"])
    def execute(self, request, *args, **kwargs):
        execution, created = DashboardReportExecutionService.execute_manual(
            request,
            self.get_object(),
        )
        return Response(
            {
                "execution_id": execution.id,
                "status": execution.status,
                "request_id": execution.request_id,
                "created": created,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )
