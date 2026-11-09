from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import VictoriaTracesTelemetryStore
from apps.apm.adapters.aggregate_red import apm_availability_slo_store, apm_entry_red_store
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import ApmDashboardQuerySerializer
from apps.apm.services.access import visible_organization_ids
from apps.apm.services.dashboard import ApmDashboardService
from apps.apm.services.reliability import DjangoApmReliabilityService
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
        serializer = ApmDashboardQuerySerializer(data=request.query_params, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        traces = VictoriaTracesTelemetryStore()
        service = ApmDashboardService(
            metric_store=traces,
            red_store=apm_entry_red_store(traces=traces),
            reliability=DjangoApmReliabilityService(apm_availability_slo_store(traces=traces)),
        )
        return Response(
            service.build(
                organization_ids=organization_ids,
                window=serializer.validated_data["window"],
            )
        )
