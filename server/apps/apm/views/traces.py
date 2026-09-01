from __future__ import annotations

import re
from dataclasses import replace

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.adapters.victoriatraces import _encode_cursor
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import TraceSearchSerializer
from apps.apm.services import DjangoTelemetryQueryService
from apps.apm.services.access import visible_organization_ids
from apps.apm.services.contracts import SpanDetail, TraceDetail, TraceSearchQuery, TraceSummary
from apps.apm.services.trace_access import TraceAccessResolver, collect_visible_page
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
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
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
            service_name=data.get("service_name"),
            environment=data.get("environment"),
            instance_id=data.get("instance_id"),
            span_name=data.get("span_name"),
            status=data.get("status"),
            min_duration_ms=data.get("min_duration_ms"),
            max_duration_ms=data.get("max_duration_ms"),
            cursor=data.get("cursor"),
            limit=data["limit"],
        )
        query_service = self._query_service()

        def fetch_page(cursor: str | None):
            page = query_service.search_traces(replace(query, cursor=cursor))
            return page.items, page.next_cursor

        try:
            visible, next_cursor = collect_visible_page(
                fetch_page=fetch_page,
                filter_items=lambda items: self.access.filter_summaries(items, organization_ids),
                cursor=query.cursor,
                limit=query.limit,
                encode_cursor=lambda item: _encode_cursor(item.started_at),
            )
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
        return Response({"items": [_summary_data(item) for item in visible], "next_cursor": next_cursor})

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
        organization_ids = visible_organization_ids(request)
        if detail is None or not organization_ids or not self.access.can_view_detail(detail, organization_ids):
            raise Http404
        return Response(_detail_data(detail))
