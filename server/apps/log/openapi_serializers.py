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


class LogCollectTypeQuerySerializer(LogGroupQuerySerializer):
    """日志集成列表里的采集类型，以及该类型要填写的字段。"""


class LogCollectInstanceCreateSerializer(OpenAPIRequestSerializer):
    """在节点上创建日志采集实例和配置并下发。组织由令牌决定。"""

    collect_type_id = serializers.IntegerField(min_value=1)
    instances = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    configs = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class LogCollectConfigUpdateSerializer(OpenAPIRequestSerializer):
    """修改已有日志采集配置并重新下发。"""

    instance_id = serializers.CharField(max_length=200)
    collect_type_id = serializers.IntegerField(min_value=1)
    child = serializers.DictField(required=False)
    base = serializers.DictField(required=False)

    def validate(self, attrs):
        if not attrs.get("child") and not attrs.get("base"):
            raise serializers.ValidationError("需要提供 child 或 base 配置")
        return attrs


class LogCollectInstanceDeleteSerializer(OpenAPIRequestSerializer):
    """移除本组织的日志采集实例及其配置。"""

    instance_ids = serializers.ListField(child=serializers.CharField(max_length=200), allow_empty=False)


class LogK8sCollectorCreateSerializer(OpenAPIRequestSerializer):
    """日志 Kubernetes 接入向导里创建采集实例。"""

    collect_type_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200)
    instance_id = serializers.CharField(required=False, allow_blank=False, max_length=200)


class K8sDaemonSetTolerationSerializer(OpenAPIRequestSerializer):
    """DaemonSet 容忍项。只声明 key、effect、value；服务层继续做 Kubernetes 名称校验。"""

    key = serializers.CharField()
    effect = serializers.ChoiceField(choices=("NoSchedule", "NoExecute"))
    value = serializers.CharField(required=False, allow_blank=True)


class LogK8sSettingSerializer(OpenAPIRequestSerializer):
    """保存日志 Kubernetes 采集范围。"""

    instance_id = serializers.CharField(max_length=200)
    runtime_profile = serializers.ChoiceField(choices=("standard", "docker", "custom"))
    host_log_path = serializers.CharField(required=False, allow_blank=True, max_length=500)
    docker_container_log_path = serializers.CharField(required=False, allow_blank=True, max_length=500)
    namespace_patterns = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    pod_patterns = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    tolerations = serializers.ListField(child=K8sDaemonSetTolerationSerializer(), required=False, max_length=16)


class LogK8sInstallCommandSerializer(OpenAPIRequestSerializer):
    """生成复制到集群执行的日志采集安装命令。"""

    instance_id = serializers.CharField(max_length=200)
    cloud_region_id = serializers.IntegerField(min_value=1)
    image_registry_prefix = serializers.CharField(required=False, allow_blank=True, max_length=200)
    tolerations = serializers.ListField(child=K8sDaemonSetTolerationSerializer(), required=False, max_length=16)


class LogK8sStatusQuerySerializer(OpenAPIRequestSerializer):
    """检查日志 Kubernetes 采集是否已经上报。"""

    instance_id = serializers.CharField(max_length=200)
