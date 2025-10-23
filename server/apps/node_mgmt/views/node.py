from django.core.cache import cache
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.filters.node import NodeFilter
from apps.node_mgmt.models.sidecar import Node
from config.drf.pagination import CustomPageNumberPagination
from apps.node_mgmt.serializers.node import NodeSerializer, BatchBindingNodeConfigurationSerializer, \
    BatchOperateNodeCollectorSerializer
from apps.node_mgmt.services.node import NodeService


class NodeViewSet(mixins.DestroyModelMixin,
                  mixins.ListModelMixin,
                  GenericViewSet):
    queryset = Node.objects.all().prefetch_related('nodeorganization_set').order_by("-created_at")
    filterset_class = NodeFilter
    pagination_class = CustomPageNumberPagination
    serializer_class = NodeSerializer
    search_fields = ["id", "name", "ip"]

    def add_permission(self, permission, items):
        node_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for node_info in items:
            if node_info["id"] in node_permission_map:
                node_info["permission"] = node_permission_map[node_info["id"]]
            else:
                node_info["permission"] = NodeConstants.DEFAULT_PERMISSION


    def list(self, request, *args, **kwargs):
        # 获取权限规则
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "node_mgmt",
            NodeConstants.MODULE,
        )

        # 应用权限过滤
        queryset = permission_filter(Node, permission, team_key="nodeorganization__organization__in", id_key="id__in")
        queryset = self.filter_queryset(queryset)

        # 根据组织筛选
        organization_ids = request.query_params.get('organization_ids')
        if organization_ids:
            organization_ids = organization_ids.split(',')
            queryset = queryset.filter(nodeorganization__organization__in=organization_ids).distinct()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = NodeSerializer(page, many=True)
            node_data = serializer.data
            processed_data = NodeService.process_node_data(node_data)

            # 添加权限信息到每个节点
            self.add_permission(permission, processed_data)

            return self.get_paginated_response(processed_data)

        serializer = NodeSerializer(queryset, many=True)
        node_data = serializer.data
        processed_data = NodeService.process_node_data(node_data)

        # 添加权限信息到每个节点
        self.add_permission(permission, processed_data)

        return WebUtils.response_success(processed_data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return WebUtils.response_success()

    @action(methods=["get"], detail=False, url_path=r"enum", filter_backends=[])
    def enum(self, request, *args, **kwargs):
        return WebUtils.response_success(dict(sidecar_status=ControllerConstants.SIDECAR_STATUS_ENUM))

    @action(detail=False, methods=["post"], url_path="batch_binding_configuration")
    def batch_binding_node_configuration(self, request):
        serializer = BatchBindingNodeConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_configuration_id = serializer.validated_data["collector_configuration_id"]
        result, message = NodeService.batch_binding_node_configuration(node_ids, collector_configuration_id)

        # 清除cache中的etag
        for node_id in node_ids:
            cache.delete(f"node_etag_{node_id}")

        if result:
            return WebUtils.response_success(message)
        else:
            return WebUtils.response_error(error_message=message)

    @action(detail=False, methods=["post"], url_path="batch_operate_collector")
    def batch_operate_node_collector(self, request):
        serializer = BatchOperateNodeCollectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_id = serializer.validated_data["collector_id"]
        operation = serializer.validated_data["operation"]
        NodeService.batch_operate_node_collector(node_ids, collector_id, operation)

        # 清除cache中的etag
        for node_id in node_ids:
            cache.delete(f"node_etag_{node_id}")

        return WebUtils.response_success()

    @action(detail=False, methods=["post"], url_path="node_config_asso")
    def get_node_config_asso(self, request):
        nodes = Node.objects.prefetch_related("collectorconfiguration_set").filter(cloud_region_id=request.data["cloud_region_id"])
        if request.data.get("ids"):
            nodes = nodes.filter(id__in=request.data["ids"])

        result = [
            {
                "id": node.id,
                "name": node.name,
                "ip": node.ip,
                "operating_system": node.operating_system,
                "cloud_region_id": node.cloud_region_id,
                "configs": [
                    {
                        "id": cfg.id,
                        "name": cfg.name,
                        "collector_id": cfg.collector_id,
                        "is_pre": cfg.is_pre,
                    }
                    for cfg in node.collectorconfiguration_set.all()
                ],
            }
            for node in nodes
        ]

        return WebUtils.response_success(result)
