from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.child_config.common import ChildConfigCommon
from apps.node_mgmt.filters.child_config import ChildConfigFilter
from apps.node_mgmt.models import ChildConfig
from apps.node_mgmt.serializers.child_config import ChildConfigSerializer


class ChildConfigViewSet(ModelViewSet):

    queryset = ChildConfig.objects.all()
    serializer_class = ChildConfigSerializer
    filterset_class = ChildConfigFilter

    @swagger_auto_schema(
        operation_id="batch_setting_node_config",
        operation_summary="批量设置节点配置",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "object_type": openapi.Schema(type=openapi.TYPE_STRING, description="对象类型"),
                "nodes": openapi.Schema(
                    type=openapi.TYPE_ARRAY, description="节点列表",
                    items=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                        "id": openapi.Schema(type=openapi.TYPE_STRING, description="节点id"),
                        "configs": openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_STRING), description="配置列表"),
                    })
                ),
            },
            required=["object_type", "nodes"]
        ),
        tags=['ChildConfig']
    )
    @action(detail=False, methods=["post"], url_path="batch_setting_node_config")
    def batch_setting_node_config(self, request):
        object_type = request.data.get('object_type')
        nodes = request.data.get('nodes')
        ChildConfigCommon(object_type).batch_setting_node_config(nodes)
        return WebUtils.response_success()
