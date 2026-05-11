from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import MaintainerViewSet
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.models.sidecar import CollectorConfiguration, Node
from apps.node_mgmt.serializers.collector_configuration import (
    CollectorConfigurationSerializer,
    CollectorConfigurationCreateSerializer,
    CollectorConfigurationUpdateSerializer,
    BulkDeleteConfigurationSerializer,
)
from apps.node_mgmt.filters.collector_configuration import CollectorConfigurationFilter
from apps.node_mgmt.services.collector_configuration import (
    CollectorConfigurationService,
)
from apps.node_mgmt.utils.permission import (
    authorize_collector_configuration_ids,
    authorize_mutable_collector_configuration_ids,
    authorize_node_ids,
    get_authorized_collector_configuration_queryset,
    get_mutable_collector_configuration_queryset,
    get_authorized_node_queryset,
)


class CollectorConfigurationViewSet(MaintainerViewSet):
    queryset = CollectorConfiguration.objects.all().order_by("-created_at")
    serializer_class = CollectorConfigurationSerializer
    filterset_class = CollectorConfigurationFilter
    search_fields = ["id", "name"]

    def get_queryset(self):
        if self.action in {"update", "partial_update", "destroy"}:
            return get_mutable_collector_configuration_queryset(self.request).order_by("-created_at")
        return get_authorized_collector_configuration_queryset(self.request).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict) and "items" in response.data:
            response.data["items"] = CollectorConfigurationService.calculate_node_count(response.data["items"])
        else:
            response.data = CollectorConfigurationService.calculate_node_count(response.data)
        return response

    @action(detail=False, methods=["post"], url_path="config_node_asso")
    def get_config_node_asso(self, request):
        queryset = get_authorized_node_queryset(request)
        node_ids = list(queryset.distinct().values_list("id", flat=True))
        if not node_ids:
            return WebUtils.response_success([])
        authorized_node_ids = set(node_ids)

        qs = (
            CollectorConfiguration.objects.select_related("collector")
            .prefetch_related("nodes")
            .filter(
                nodes__id__in=node_ids,
            )
        )

        if request.data.get("ids"):
            qs = qs.filter(id__in=request.data["ids"])
        if request.data.get("node_id"):
            qs = qs.filter(nodes__id=request.data["node_id"])
        if request.data.get("name"):
            qs = qs.filter(name__icontains=request.data["name"])

        if not qs:
            return WebUtils.response_success([])

        result = [
            dict(
                id=obj.id,
                name=obj.name,
                config_template=obj.config_template,
                collector_id=obj.collector_id,
                cloud_region_id=obj.cloud_region_id,
                is_pre=obj.is_pre,
                operating_system=obj.collector.node_operating_system,
                nodes=[
                    {
                        "id": node.id,
                        "name": node.name,
                        "ip": node.ip,
                        "operating_system": node.operating_system,
                    }
                    for node in obj.nodes.all()
                    if node.id in authorized_node_ids
                ],
            )
            for obj in qs
        ]
        return WebUtils.response_success(result)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def create(self, request, *args, **kwargs):
        self.serializer_class = CollectorConfigurationCreateSerializer
        return super().create(request, *args, **kwargs)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = CollectorConfigurationUpdateSerializer
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("cloud_region_node-EditMainConfiguration")
    def update(self, request, *args, **kwargs):
        self.serializer_class = CollectorConfigurationUpdateSerializer
        return super().update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(methods=["post"], detail=False, url_path="bulk_delete")
    @HasPermission("cloud_region_node-EditMainConfiguration")
    def bulk_delete(self, request):
        serializer = BulkDeleteConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        configurations, error_response = authorize_mutable_collector_configuration_ids(request, ids)
        if error_response:
            return error_response
        CollectorConfiguration.objects.filter(id__in=[config.id for config in configurations]).delete()
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="apply_to_node")
    @HasPermission("cloud_region_node-EditMainConfiguration")
    def apply_to_node(self, request):
        node_ids = [item["node_id"] for item in request.data]
        config_ids = [item["collector_configuration_id"] for item in request.data]
        _, error_response = authorize_node_ids(request, node_ids)
        if error_response:
            return error_response
        _, error_response = authorize_mutable_collector_configuration_ids(request, config_ids)
        if error_response:
            return error_response

        result = []
        for item in request.data:
            collector_configuration_id = item["collector_configuration_id"]
            node_id = item["node_id"]
            success, message = CollectorConfigurationService.apply_to_node(node_id, collector_configuration_id)
            result.append(
                {
                    "node_id": node_id,
                    "collector_configuration_id": collector_configuration_id,
                    "success": success,
                    "message": message,
                }
            )

        return WebUtils.response_success(result)

    @action(methods=["post"], detail=False, url_path="cancel_apply_to_node")
    @HasPermission("cloud_region_node-EditMainConfiguration")
    def cancel_apply_to_node(self, request):
        config_id = request.data["collector_configuration_id"]
        node_id = request.data["node_id"]
        nodes, error_response = authorize_node_ids(request, [node_id])
        if error_response:
            return error_response
        configurations, error_response = authorize_mutable_collector_configuration_ids(request, [config_id])
        if error_response:
            return error_response
        try:
            config = configurations[0]
            node = nodes[0]
            config.nodes.remove(node)
            return WebUtils.response_success()
        except Exception as e:
            return WebUtils.response_error(error_message=str(e))
