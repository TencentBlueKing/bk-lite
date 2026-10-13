"""apm 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import PaginatedRequestSerializer


class ApmPageQuerySerializer(PaginatedRequestSerializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class ApmApplicationQuerySerializer(ApmPageQuerySerializer):
    """APM 应用列表。组织身份只允许由网关注入。"""


class ApmServiceQuerySerializer(ApmPageQuerySerializer):
    """APM 服务列表。组织身份只允许由网关注入。"""

    application_id = serializers.CharField(required=False, max_length=128)


class ApmInstanceQuerySerializer(ApmPageQuerySerializer):
    """APM 服务实例列表。组织身份只允许由网关注入。"""

    application_id = serializers.CharField(required=False, max_length=128)
