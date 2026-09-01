from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import VictoriaTracesTelemetryStore
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import ApmDashboardQuerySerializer
from apps.apm.services.access import visible_organization_ids
from apps.apm.services.dashboard import ApmDashboardService
from apps.core.decorators.api_permission import HasPermission


class ApmDashboardViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)

    @HasPermission("home-View,services-View")
    def list(self, request, *args, **kwargs):
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
            return Response(
                {
                    "empty": True,
                    "window": "1h",
                    "kpis": {"status": "empty"},
                    "health": {"status": "empty"},
                    "slos": {"status": "empty"},
                    "alerts": {"status": "empty"},
                    "top_error_rate": {"status": "empty"},
                    "top_p95": {"status": "empty"},
                    "releases": {"status": "empty", "data": {"items": []}},
                }
            )
        serializer = ApmDashboardQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = ApmDashboardService(metric_store=VictoriaTracesTelemetryStore())
        return Response(
            service.build(
                organization_ids=organization_ids,
                window=serializer.validated_data["window"],
            )
        )
