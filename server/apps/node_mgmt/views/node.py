from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants import SIDECAR_STATUS_ENUM
from apps.node_mgmt.filters.node import NodeFilter
from apps.node_mgmt.models.sidecar import Node
from config.drf.pagination import CustomPageNumberPagination
from apps.node_mgmt.serializers.node import NodeSerializer, BatchBindingNodeConfigurationSerializer, \
    BatchOperateNodeCollectorSerializer
from apps.node_mgmt.services.node import NodeService
from drf_yasg import openapi


class NodeViewSet(mixins.DestroyModelMixin,
                  mixins.ListModelMixin,
                  GenericViewSet):
    queryset = Node.objects.all().order_by("-created_at")
    filterset_class = NodeFilter
    pagination_class = CustomPageNumberPagination
    serializer_class = NodeSerializer
    search_fields = ["id", "name", "ip"]

    @swagger_auto_schema(
        operation_id="node_list",
        operation_summary="获取节点列表",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="模糊搜索(id, name, ip)",
                              type=openapi.TYPE_STRING),
            openapi.Parameter('cloud_region_id', openapi.IN_QUERY, description="云区域ID", type=openapi.TYPE_INTEGER,
                              required=True),
            openapi.Parameter('organization_ids', openapi.IN_QUERY, description="组织ID列表(用逗号分隔)", type=openapi.TYPE_STRING),
        ],
        tags=['Node']
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

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
            return self.get_paginated_response(processed_data)

        serializer = NodeSerializer(queryset, many=True)
        node_data = serializer.data
        processed_data = NodeService.process_node_data(node_data)
        return WebUtils.response_success(processed_data)

    @swagger_auto_schema(
        operation_id="node_del",
        operation_summary="删除节点",
        tags=['Node']
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="node_enum",
        operation_summary="节点管理的状态枚举值",
        tags=['Node']
    )
    @action(methods=["get"], detail=False, url_path=r"enum", filter_backends=[])
    def enum(self, request, *args, **kwargs):
        return WebUtils.response_success(dict(sidecar_status=SIDECAR_STATUS_ENUM))

    @swagger_auto_schema(
        operation_id="nodes_binding_configuration",
        operation_summary="批量绑定或更新节点的采集器配置",
        request_body=BatchBindingNodeConfigurationSerializer,
        tags=['Node']
    )
    @action(detail=False, methods=["post"], url_path="batch_binding_configuration")
    def batch_binding_node_configuration(self, request):
        serializer = BatchBindingNodeConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_configuration_id = serializer.validated_data["collector_configuration_id"]
        result, message = NodeService.batch_binding_node_configuration(node_ids, collector_configuration_id)
        if result:
            return WebUtils.response_success(message)
        else:
            return WebUtils.response_error(error_message=message)

    @swagger_auto_schema(
        operation_id="batch_operate_node_collector",
        operation_summary="批量操作节点的采集器(包括start, stop, restart)",
        request_body=BatchOperateNodeCollectorSerializer,
        tags=['Node']
    )
    @action(detail=False, methods=["post"], url_path="batch_operate_collector")
    def batch_operate_node_collector(self, request):
        serializer = BatchOperateNodeCollectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_ids = serializer.validated_data["node_ids"]
        collector_id = serializer.validated_data["collector_id"]
        operation = serializer.validated_data["operation"]
        NodeService.batch_operate_node_collector(node_ids, collector_id, operation)
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_summary="查询节点信息以及关联的配置",
        operation_id="node_config_asso",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "cloud_region_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="云区域ID"),
                "ids": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING,description="节点id")),
            },
            required=["cloud_region_id"]
        ),
    )
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
