"""apm 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


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


class ApmServiceMetricQuerySerializer(OpenAPIRequestSerializer):
    """服务请求量、错误率和耗时。时间窗最长 7 天。"""

    service_id = serializers.CharField(max_length=64)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    environment = serializers.CharField(required=False, default="", allow_blank=True, max_length=256)


class ApmTraceQuerySerializer(OpenAPIRequestSerializer):
    """调用摘要。时间窗最长 1 小时，单次最多 100 条。"""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    service_id = serializers.CharField(required=False, max_length=64)
    status = serializers.ChoiceField(choices=("ok", "error"), required=False)
    limit = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    cursor = serializers.CharField(required=False, max_length=512)


class ApmTraceDetailQuerySerializer(OpenAPIRequestSerializer):
    """单条调用。跨组织按不存在处理。"""

    trace_id = serializers.RegexField(r"^[0-9a-fA-F]{16}(?:[0-9a-fA-F]{16})?$")
