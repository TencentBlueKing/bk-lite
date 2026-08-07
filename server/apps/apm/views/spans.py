from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import SpanSearchSerializer
from apps.apm.services import DjangoTelemetryQueryService
from apps.apm.services.access import current_organization_id
from apps.apm.services.contracts import SpanSearchQuery, SpanSummary
from apps.apm.services.trace_access import TraceAccessResolver
from apps.core.decorators.api_permission import HasPermission


def _span_summary_data(item: SpanSummary) -> dict[str, object]:
    return {
        "trace_id": item.trace_id,
        "span_id": item.span_id,
        "started_at": item.started_at,
        "duration_ms": item.duration_ms,
        "service_namespace": item.service_namespace,
        "service_name": item.service_name,
        "environment": item.environment,
        "instance_id": item.instance_id,
        "status": item.status,
        "name": item.name,
        "kind": item.kind,
        "http_method": item.http_method,
        "http_status_code": item.http_status_code,
    }


class ApmSpanViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)
    access = TraceAccessResolver()

    @staticmethod
    def _query_service() -> DjangoTelemetryQueryService:
        return DjangoTelemetryQueryService(trace_store=VictoriaTracesTelemetryStore())

    @HasPermission("traces-View")
    def list(self, request):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response({"items": [], "next_cursor": None})
        serializer = SpanSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        query = SpanSearchQuery(
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            service_name=data["service_name"],
            environment=data["environment"],
            service_namespace=data.get("service_namespace"),
            instance_id=data.get("instance_id"),
            span_name=data.get("span_name"),
            status=data.get("status"),
            kind=data.get("kind"),
            min_duration_ms=data.get("min_duration_ms"),
            max_duration_ms=data.get("max_duration_ms"),
            cursor=data.get("cursor"),
            limit=data["limit"],
        )
        try:
            page = self._query_service().search_spans(query)
        except ValueError as exc:
            return Response(
                {"code": "invalid_query", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"detail": str(exc), "code": "telemetry_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        visible = self.access.filter_span_summaries(page.items, organization_id)
        return Response({"items": [_span_summary_data(item) for item in visible], "next_cursor": page.next_cursor})
