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


class ApmApplicationCreateSerializer(OpenAPIRequestSerializer):
    """接入页创建应用。组织归属强制为令牌绑定组织。"""

    application_id = serializers.RegexField(regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", max_length=128)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, max_length=512)


class ApmApplicationResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(allow_blank=True, max_length=512)


class ApmApplicationPageResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    page_size = serializers.IntegerField(min_value=1)
    items = ApmApplicationResponseSerializer(many=True)


class ApmIntegrationRegionQuerySerializer(OpenAPIRequestSerializer):
    """接入页可选云区域，以及该区域能否接收遥测。调用仍须绑定组织。"""


class ApmIntegrationConfigSerializer(OpenAPIRequestSerializer):
    """按语言、运行时和云区域生成接入配置，不保存。"""

    application_id = serializers.CharField(max_length=128)
    cloud_region_id = serializers.IntegerField(min_value=1)
    language = serializers.ChoiceField(choices=("python", "nodejs", "java", "go", "dotnet"))
    runtime = serializers.ChoiceField(choices=("kubernetes", "docker", "host", "other"))
    service_name = serializers.CharField(max_length=256)
    service_version = serializers.CharField(required=False, allow_blank=True, max_length=256)
    environment = serializers.CharField(max_length=256, allow_blank=True)
    sample_rate = serializers.IntegerField(required=False, default=100, min_value=1, max_value=100)
