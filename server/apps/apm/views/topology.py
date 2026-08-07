from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.models import ApmService, ApmServiceInstance
from apps.apm.renderers import ApmRenderer
from apps.apm.services import DjangoApmTopologyService
from apps.apm.services.access import current_organization_id, filter_current_organization
from apps.apm.services.contracts import TopologyTarget
from apps.core.decorators.api_permission import HasPermission


class TopologyQuerySerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=False)

    def validate(self, attrs):
        unsupported = sorted(set(self.initial_data) - set(self.fields))
        if unsupported:
            raise serializers.ValidationError(f"不支持的拓扑查询参数: {', '.join(unsupported)}")
        ended_at = attrs.get("ended_at") or timezone.now()
        started_at = attrs.get("started_at") or ended_at - timedelta(hours=1)
        if ended_at <= started_at:
            raise serializers.ValidationError("查询结束时间必须晚于开始时间")
        if ended_at - started_at > timedelta(days=7):
            raise serializers.ValidationError("拓扑查询时间窗不能超过 7 天")
        attrs.update(started_at=started_at, ended_at=ended_at)
        return attrs


class ApmTopologyViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)

    @staticmethod
    def _service():
        return DjangoApmTopologyService(VictoriaTracesTelemetryStore())

    @HasPermission("services-View")
    def list(self, request):
        organization_id = current_organization_id(request)
        if organization_id is None:
            return Response({"nodes": [], "edges": [], "sampled_traces": 0, "truncated": False, "data_state": "no_data"})
        serializer = TopologyQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(
                {"code": "invalid_query", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = serializer.validated_data
        services = filter_current_organization(
            ApmService.objects.filter(archived_at__isnull=True),
            request,
            "organization_links",
        )
        instances = ApmServiceInstance.objects.select_related("service").filter(
            service__in=services,
            archived_at__isnull=True,
        )
        if environment := data.get("environment"):
            instances = instances.filter(environment=environment)
        target_rows = (
            instances.values("service_id", "service__namespace", "service__name", "environment")
            .order_by("service_id", "environment")
            .distinct()
        )
        targets = [TopologyTarget(row["service__namespace"], row["service__name"], row["environment"]) for row in target_rows]
        try:
            graph = self._service().build(
                targets,
                started_at=data["started_at"],
                ended_at=data["ended_at"],
            )
        except ValueError as exc:
            return Response({"code": "invalid_query", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TelemetryStoreUnavailable as exc:
            return Response(
                {"code": "telemetry_unavailable", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(asdict(graph))
