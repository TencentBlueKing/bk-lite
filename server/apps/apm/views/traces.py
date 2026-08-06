from __future__ import annotations

import re

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import TraceSearchSerializer
from apps.apm.services import DjangoTelemetryQueryService
from apps.apm.services.access import current_organization_id
from apps.apm.services.contracts import SpanDetail, TraceDetail, TraceSearchQuery, TraceSummary
from apps.apm.services.trace_access import TraceAccessResolver
from apps.core.decorators.api_permission import HasPermission


_TRACE_ID_RE = re.compile(r"^[0-9a-fA-F]{16}(?:[0-9a-fA-F]{16})?$")


def _summary_data(item: TraceSummary) -> dict[str, object]:
    return {
        "trace_id": item.trace_id,
        "started_at": item.started_at,
        "duration_ms": item.duration_ms,
        "service_namespace": item.service_namespace,
        "service_name": item.service_name,
        "environment": item.environment,
        "instance_id": item.instance_id,
        "status": item.status,
        "root_span_name": item.root_span_name,
        "span_count": item.span_count,
    }


def _span_data(span: SpanDetail) -> dict[str, object]:
    return {
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "started_at": span.started_at,
        "duration_ms": span.duration_ms,
        "status": span.status,
        "attributes": span.attributes,
        "service_namespace": span.service_namespace,
        "service_name": span.service_name,
        "environment": span.environment,
        "instance_id": span.instance_id,
        "kind": span.kind,
    }


def _detail_data(detail: TraceDetail) -> dict[str, object]:
    return {
        "trace_id": detail.trace_id,
        "service_namespace": detail.service_namespace,
        "service_name": detail.service_name,
        "environment": detail.environment,
        "instance_id": detail.instance_id,
        "truncated": detail.truncated,
        "spans": [_span_data(span) for span in detail.spans],
    }


class ApmTraceViewSet(viewsets.ViewSet):
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
        serializer = TraceSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        query = TraceSearchQuery(
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            service_namespace=data.get("service_namespace"),
            service_name=data["service_name"],
            environment=data["environment"],
            instance_id=data.get("instance_id"),
            cursor=data.get("cursor"),
            limit=data["limit"],
        )
        try:
            page = self._query_service().search_traces(query)
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
        visible = self.access.filter_summaries(page.items, organization_id)
        return Response({"items": [_summary_data(item) for item in visible], "next_cursor": page.next_cursor})

    @HasPermission("traces-View")
    def retrieve(self, request, pk=None):
        if not pk or not _TRACE_ID_RE.fullmatch(pk):
            raise Http404
        try:
            detail = self._query_service().get_trace(pk.lower())
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"detail": str(exc), "code": "telemetry_unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        organization_id = current_organization_id(request)
        if detail is None or organization_id is None or not self.access.can_view_detail(detail, organization_id):
            raise Http404
        return Response(_detail_data(detail))
