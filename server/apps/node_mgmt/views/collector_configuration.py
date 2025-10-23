from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action

from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.sidecar import CollectorConfiguration, Node
from apps.node_mgmt.serializers.collector_configuration import (
    CollectorConfigurationSerializer,
    CollectorConfigurationCreateSerializer,
    CollectorConfigurationUpdateSerializer, BulkDeleteConfigurationSerializer, ApplyToNodeSerializer
)
from apps.node_mgmt.filters.collector_configuration import CollectorConfigurationFilter
from apps.node_mgmt.services.collector_configuration import CollectorConfigurationService
from django.core.cache import cache


class CollectorConfigurationViewSet(ModelViewSet):
    queryset = CollectorConfiguration.objects.all().order_by("-created_at")
    serializer_class = CollectorConfigurationSerializer
    filterset_class = CollectorConfigurationFilter
    search_fields = ['id', 'name']

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict) and 'items' in response.data:
            response.data['items'] = CollectorConfigurationService.calculate_node_count(response.data['items'])
        else:
            response.data = CollectorConfigurationService.calculate_node_count(response.data)
        return response

    @action(detail=False, methods=["post"], url_path="config_node_asso")
    def get_config_node_asso(self, request):

        # 获取用户节点权限列表
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "node_mgmt",
            NodeConstants.MODULE,
        )
        queryset = permission_filter(Node, permission, team_key="nodeorganization__organization__in", id_key="id__in")
        node_ids = list(queryset.values_list("id", flat=True).distinct())
        if not node_ids:
            return WebUtils.response_success([])

        qs = CollectorConfiguration.objects.select_related("collector").prefetch_related("nodes").filter(
            cloud_region_id=request.data["cloud_region_id"],
            nodes__id__in=node_ids,     # 权限
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
                ],
            )
            for obj in qs
        ]
        return WebUtils.response_success(result)

    def create(self, request, *args, **kwargs):
        # 清除cache中的etag
        pk = kwargs.get('pk')
        cache.delete(f"configuration_etag_{pk}")
        self.serializer_class = CollectorConfigurationCreateSerializer
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        # 清除cache中的etag
        pk = kwargs.get('pk')
        cache.delete(f"configuration_etag_{pk}")
        self.serializer_class = CollectorConfigurationUpdateSerializer
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):

        return super().update(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(methods=['post'], detail=False, url_path='bulk_delete')
    def bulk_delete(self, request):
        serializer = BulkDeleteConfigurationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['ids']
        CollectorConfiguration.objects.filter(id__in=ids).delete()
        return WebUtils.response_success()

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
