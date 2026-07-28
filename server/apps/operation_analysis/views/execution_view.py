from rest_framework import mixins, viewsets

from apps.core.decorators.api_permission import HasPermission
from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)
from apps.operation_analysis.serializers.execution_serializers import (
    DashboardReportExecutionSerializer,
)


class DashboardReportExecutionViewSet(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DashboardReportExecutionSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        queryset = DashboardReportExecution.objects.select_related(
            "subscription",
            "dashboard",
        )
        if not getattr(self.request.user, "is_superuser", False):
            queryset = queryset.filter(creator=self.request.user.username)
        return queryset

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
