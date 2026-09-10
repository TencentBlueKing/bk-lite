from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.response import Response

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore, telemetry_error_payload
from apps.apm.models import ApmService, ApmServiceInstance
from apps.apm.renderers import ApmRenderer
from apps.apm.services import DjangoApmTopologyService
from apps.apm.services.access import visible_organization_ids, filter_current_organization
from apps.apm.services.contracts import TopologyTarget
from apps.core.decorators.api_permission import HasPermission


class TopologyQuerySerializer(serializers.Serializer):
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    environment = serializers.CharField(max_length=256, required=False, allow_blank=False)
    status = serializers.ChoiceField(choices=("ok", "error"), required=False)
    span_name = serializers.CharField(max_length=512, required=False, allow_blank=True)
    min_duration_ms = serializers.FloatField(required=False, min_value=0)
    include_inferred = serializers.BooleanField(required=False, default=False)
    include_user_request = serializers.BooleanField(required=False, default=False)
    application_id = serializers.CharField(max_length=128, required=False, allow_blank=False)

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
        if attrs.get("span_name") == "":
            attrs.pop("span_name", None)
        attrs.update(started_at=started_at, ended_at=ended_at)
        return attrs


class ApmTopologyViewSet(viewsets.ViewSet):
    renderer_classes = (ApmRenderer,)

    @staticmethod
    def _service():
        store = VictoriaTracesTelemetryStore()
        return DjangoApmTopologyService(store)

    @HasPermission("services-View")
    def list(self, request):
        if not visible_organization_ids(request):
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
        )
        if environment := data.get("environment"):
            instances = instances.filter(environment=environment)
        target_rows = list(
            instances.values(
                "service_id",
                "service__namespace",
                "service__name",
                "service__language",
                "service__application__application_id",
                "environment",
            )
            .order_by("service_id", "environment")
            .distinct()
        )
        application_id = data.get("application_id")
        sample_service_names = None
        if application_id:
            app_rows = [row for row in target_rows if row["service__application__application_id"] == application_id]
            other_rows = [row for row in target_rows if row["service__application__application_id"] != application_id]
            target_rows = app_rows + other_rows
            sample_service_names = tuple(dict.fromkeys(row["service__name"] for row in app_rows if row["service__name"]))
        targets = [
            TopologyTarget(
                row["service__namespace"],
                row["service__name"],
                row["environment"],
                row["service__language"],
            )
            for row in target_rows
        ]
        try:
            graph = self._service().build(
                targets,
                started_at=data["started_at"],
                ended_at=data["ended_at"],
                environment=data.get("environment"),
                status=data.get("status"),
                span_name=data.get("span_name"),
                min_duration_ms=data.get("min_duration_ms"),
                include_inferred=bool(data.get("include_inferred")),
                include_user_request=bool(data.get("include_user_request")),
                sample_service_names=sample_service_names,
            )
        except ValueError as exc:
            return Response({"code": "invalid_query", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except TelemetryStoreUnavailable as exc:
            return Response(telemetry_error_payload(exc), status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(asdict(graph))
