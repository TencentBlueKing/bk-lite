from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.operation_analysis.serializers.scene_widget_serializers import (
    Application3DAlarmDetailRequestSerializer,
    Application3DApplicationDetailRequestSerializer,
    Application3DMetricRequestSerializer,
    Application3DWallRequestSerializer,
    NetworkStatusTopologyRequestSerializer,
)
from apps.operation_analysis.services.application3d import Application3DQueryService
from apps.operation_analysis.services.application3d.errors import Application3DError
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService


class SceneWidgetViewSet(ViewSet):
    _APPLICATION3D_ERROR_STATUS = {
        "invalid_request": status.HTTP_400_BAD_REQUEST,
        "permission_denied": status.HTTP_403_FORBIDDEN,
        "not_found": status.HTTP_404_NOT_FOUND,
        "scope_changed": status.HTTP_409_CONFLICT,
        "source_failure": status.HTTP_502_BAD_GATEWAY,
        "capacity_exceeded": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }

    @classmethod
    def application3d_error_response(cls, exc: Application3DError):
        return Response(
            {"code": exc.code, "detail": exc.message, **exc.extra},
            status=cls._APPLICATION3D_ERROR_STATUS.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        )

    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="network_status_topology")
    def network_status_topology(self, request):
        serializer = NetworkStatusTopologyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = NetworkStatusTopologyService.build(
            request=request,
            inst_uuids=[str(value) for value in data["inst_uuids"]],
            node_limit=data["node_limit"],
        )
        return Response(result)

    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="application3d/wall")
    def application3d_wall(self, request):
        serializer = Application3DWallRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                Application3DQueryService.wall(
                    request,
                    applied_filters=serializer.validated_data.get("applied_filters"),
                )
            )
        except Application3DError as exc:
            return self.application3d_error_response(exc)

    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="application3d/application_detail")
    def application3d_application_detail(self, request):
        serializer = Application3DApplicationDetailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                Application3DQueryService.application_detail(
                    request,
                    application_id=str(serializer.validated_data["application_id"]),
                )
            )
        except Application3DError as exc:
            return self.application3d_error_response(exc)

    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="application3d/alarm_detail")
    def application3d_alarm_detail(self, request):
        serializer = Application3DAlarmDetailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                Application3DQueryService.alarm_detail(
                    request,
                    application_id=str(serializer.validated_data["application_id"]),
                    alarm_id=serializer.validated_data["alarm_id"],
                )
            )
        except Application3DError as exc:
            return self.application3d_error_response(exc)

    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="application3d/metric")
    def application3d_metric(self, request):
        serializer = Application3DMetricRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                Application3DQueryService.metric_series(
                    request,
                    application_id=str(serializer.validated_data["application_id"]),
                    alarm_id=serializer.validated_data["alarm_id"],
                )
            )
        except Application3DError as exc:
            return self.application3d_error_response(exc)
