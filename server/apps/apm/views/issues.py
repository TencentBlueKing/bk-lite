from __future__ import annotations

from dataclasses import asdict

from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.renderers import ApmRenderer
from apps.apm.serializers import IssueSearchSerializer
from apps.apm.services import DjangoTelemetryIssueService, DjangoTelemetryQueryService
from apps.apm.services.access import visible_organization_ids
from apps.apm.services.contracts import IssueSearchQuery
from apps.apm.services.trace_access import TraceAccessResolver
from apps.core.decorators.api_permission import HasPermission


class ApmIssueViewSet(viewsets.ViewSet):
    """基于真实 Error Span 的有界只读 Issue 投影。"""

    renderer_classes = (ApmRenderer,)
    access = TraceAccessResolver()

    @staticmethod
    def _query_service() -> DjangoTelemetryQueryService:
        return DjangoTelemetryQueryService(trace_store=VictoriaTracesTelemetryStore())

    @HasPermission("traces-View")
    def list(self, request):
        organization_ids = visible_organization_ids(request)
        if not organization_ids:
            return Response({"items": [], "next_cursor": None, "truncated": False})
        serializer = IssueSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        query = IssueSearchQuery(
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            service_namespace=data.get("service_namespace"),
            service_name=data.get("service_name"),
            environment=data.get("environment"),
            cursor=data.get("cursor"),
            limit=data["limit"],
        )
        query_service = self._query_service()
        try:
            page = query_service.search_spans(query.span_query())
            visible = self.access.filter_span_summaries(page.items, organization_ids)
            issues = DjangoTelemetryIssueService(query_service).project(visible, next_cursor=page.next_cursor)
        except ValueError as exc:
            return Response({"code": "invalid_query", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"code": "telemetry_unavailable", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(asdict(issues))
