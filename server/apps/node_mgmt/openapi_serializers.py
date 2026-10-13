"""node 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class NodePageQuerySerializer(PaginatedRequestSerializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class NodeCloudRegionQuerySerializer(NodePageQuerySerializer):
    """云区域目录。组织身份只允许由网关注入。"""


class NodeListQuerySerializer(NodePageQuerySerializer):
    """节点列表。组织身份只允许由网关注入。"""

    cloud_region_id = serializers.IntegerField(required=False, min_value=1)


class NodeDetailQuerySerializer(OpenAPIRequestSerializer):
    """单个节点。组织身份只允许由网关注入。"""

    node_id = serializers.CharField(max_length=100)
