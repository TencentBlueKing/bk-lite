from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.models.sidecar import CollectorConfiguration, Node
from apps.node_mgmt.serializers.collector_configuration import (
    CollectorConfigurationSerializer,
    CollectorConfigurationCreateSerializer,
    CollectorConfigurationUpdateSerializer, BulkDeleteConfigurationSerializer, ApplyToNodeSerializer
)
from apps.node_mgmt.filters.collector_configuration import CollectorConfigurationFilter
from apps.node_mgmt.services.collector_configuration import CollectorConfigurationService


class CollectorConfigurationViewSet(ModelViewSet):
    queryset = CollectorConfiguration.objects.all().order_by("-created_at")
    serializer_class = CollectorConfigurationSerializer
    filterset_class = CollectorConfigurationFilter
    search_fields = ['id', 'name']

    @swagger_auto_schema(
        operation_summary="获取采集器配置列表",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="模糊搜索(id, name)",
                              type=openapi.TYPE_STRING),
            openapi.Parameter('cloud_region_id', openapi.IN_QUERY, description="云区域ID", type=openapi.TYPE_INTEGER,
                              required=True),
        ],
        tags=['CollectorConfiguration']
    )
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict) and 'items' in response.data:
            response.data['items'] = CollectorConfigurationService.calculate_node_count(response.data['items'])
        else:
            response.data = CollectorConfigurationService.calculate_node_count(response.data)
        return response

    @swagger_auto_schema(
        operation_summary="查询配置信息以及关联的节点",
        operation_id="config_node_asso",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "cloud_region_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="云区域ID"),
                "ids": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING,description="配置id")),
                "name": openapi.Schema(type=openapi.TYPE_STRING, description="配置名称"),
                "node_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="节点ID"),
            },
            required=["cloud_region_id"]
        ),
    )
    @action(detail=False, methods=["post"], url_path="config_node_asso")
    def get_config_node_asso(self, request):
        qs = CollectorConfiguration.objects.select_related("collector").prefetch_related("nodes").filter(cloud_region_id=request.data["cloud_region_id"])
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
                ],
            )
            for obj in qs
        ]
        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_summary="创建采集器配置",
        tags=['CollectorConfiguration'],
        request_body=CollectorConfigurationCreateSerializer,
    )
    def create(self, request, *args, **kwargs):
        self.serializer_class = CollectorConfigurationCreateSerializer
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="部分更新采集器配置",
        tags=['CollectorConfiguration'],
        request_body=CollectorConfigurationUpdateSerializer,
    )
    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = CollectorConfigurationUpdateSerializer
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="删除采集器配置",
        tags=['CollectorConfiguration']
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="更新采集器配置",
        tags=['CollectorConfiguration']
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="查询采集器配置详情",
        tags=['CollectorConfiguration']
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="批量删除采集器配置",
        request_body=BulkDeleteConfigurationSerializer,
        tags=['CollectorConfiguration']
    )
    @action(methods=['post'], detail=False, url_path='bulk_delete')
    def bulk_delete(self, request):
        serializer = BulkDeleteConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['ids']
        CollectorConfiguration.objects.filter(id__in=ids).delete()
        return WebUtils.response_success()

    @swagger_auto_schema(
        operation_summary="应用指定采集器配置到指定节点",
        request_body=openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "node_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="节点ID"),
                    "collector_configuration_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="采集器配置ID"),
                },
            ),
        ),
        tags=['CollectorConfiguration']
    )
    @action(methods=['post'], detail=False, url_path='apply_to_node')
    def apply_to_node(self, request):

        result = []
        for item in request.data:
            collector_configuration_id = item["collector_configuration_id"]
            node_id = item["node_id"]
            success, message = CollectorConfigurationService.apply_to_node(node_id, collector_configuration_id)
            result.append({
                "node_id": node_id,
                "collector_configuration_id": collector_configuration_id,
                "success": success,
                "message": message
            })

        return WebUtils.response_success(result)

    @swagger_auto_schema(
        operation_summary="取消应用指定采集器配置到指定节点",
        request_body=ApplyToNodeSerializer,
        tags=['CollectorConfiguration']
    )
    @action(methods=['post'], detail=False, url_path='cancel_apply_to_node')
    def cancel_apply_to_node(self, request):
        config_id = request.data["collector_configuration_id"]
        node_id = request.data["node_id"]
        try:
            config = CollectorConfiguration.objects.get(id=config_id)
            node = Node.objects.get(id=node_id)
            config.nodes.remove(node)
            return WebUtils.response_success()
        except CollectorConfiguration.DoesNotExist:
            return WebUtils.response_error(error_message="配置不存在")
        except Node.DoesNotExist:
            return WebUtils.response_error(error_message="节点不存在")
        except Exception as e:
            return WebUtils.response_error(error_message=str(e))
