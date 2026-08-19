from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.operation_analysis.serializers.scene_widget_serializers import NetworkStatusTopologyRequestSerializer
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService


class SceneWidgetViewSet(ViewSet):
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
