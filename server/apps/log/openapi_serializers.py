"""log 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class LogGroupQuerySerializer(PaginatedRequestSerializer):
    """日志分组目录。组织身份只允许由网关注入。"""

    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class LogSearchQuerySerializer(OpenAPIRequestSerializer):
    """日志检索。时间窗最长 1 小时，单次最多 100 条。"""

    log_group_id = serializers.CharField(max_length=200)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    query = serializers.CharField(required=False, default="*", max_length=512)
    limit = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
