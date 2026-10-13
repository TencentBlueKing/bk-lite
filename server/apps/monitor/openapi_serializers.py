"""monitor 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import PaginatedRequestSerializer


class MonitorPageQuerySerializer(PaginatedRequestSerializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    page_size = serializers.IntegerField(required=False, default=20, min_value=1)
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class MonitorObjectQuerySerializer(MonitorPageQuerySerializer):
    """监控对象目录。组织身份只允许由网关注入。"""


class MonitorInstanceQuerySerializer(MonitorPageQuerySerializer):
    """监控实例列表。组织身份只允许由网关注入。"""

    monitor_object_id = serializers.IntegerField(required=False, min_value=1)


class MonitorPolicyQuerySerializer(MonitorPageQuerySerializer):
    """监控策略列表。组织身份只允许由网关注入。"""

    monitor_object_id = serializers.IntegerField(required=False, min_value=1)
