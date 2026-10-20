"""monitor 对外暴露专用 serializer（schema 即契约，字段只增不删不改名）。"""

from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


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


class MonitorMetricQuerySerializer(MonitorPageQuerySerializer):
    """监控指标目录。组织身份只允许由网关注入。"""

    monitor_object_id = serializers.IntegerField(min_value=1)


class MonitorMetricValueQuerySerializer(OpenAPIRequestSerializer):
    """按指标定义查询实例当前值。不接受原始查询语句。"""

    instance_id = serializers.CharField(max_length=200)
    metric_id = serializers.IntegerField(min_value=1)


class MonitorMetricRangeQuerySerializer(MonitorMetricValueQuerySerializer):
    """按指标定义查询实例曲线。时间窗最长 6 小时。"""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    step = serializers.CharField(required=False, default="5m", max_length=16)


class MonitorPluginQuerySerializer(MonitorPageQuerySerializer):
    """集成接入列表里，某个监控对象下可选的插件。"""

    monitor_object_id = serializers.IntegerField(min_value=1)


class MonitorPluginFormQuerySerializer(OpenAPIRequestSerializer):
    """接入配置页要填写的采集参数，来自插件表单，不含查询语句。"""

    plugin_id = serializers.IntegerField(min_value=1)


class MonitorPolicyGroupQuerySerializer(MonitorPageQuerySerializer):
    """接入配置页的策略组下拉框。只查询，不创建默认组。"""

    monitor_object_id = serializers.IntegerField(min_value=1)
    plugin_id = serializers.IntegerField(required=False, min_value=1)


class MonitorPolicyGroupChoiceSerializer(OpenAPIRequestSerializer):
    """保存接入时是否加入策略组。"""

    join = serializers.BooleanField()
    group_id = serializers.IntegerField(required=False, min_value=1)


class MonitorIntegrationCreateSerializer(OpenAPIRequestSerializer):
    """主机、SNMP、脚本接入配置页的保存动作。组织由令牌决定。"""

    monitor_object_id = serializers.IntegerField(min_value=1)
    monitor_plugin_id = serializers.IntegerField(min_value=1)
    instances = serializers.ListField(child=serializers.DictField(), allow_empty=False)
    configs = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    policy_group = MonitorPolicyGroupChoiceSerializer(required=False)
    credential = serializers.DictField(required=False)


class MonitorIntegrationDeleteSerializer(OpenAPIRequestSerializer):
    """删除本组织的监控接入实例。instance_ids 取实例列表返回的 id。"""

    instance_ids = serializers.ListField(
        child=serializers.CharField(max_length=200),
        allow_empty=False,
        max_length=500,
    )


class MonitorClusterCollectorCreateSerializer(OpenAPIRequestSerializer):
    """Kubernetes 或 K3s 采集器接入向导里创建实例。collector_type 取 kubernetes 或 k3s。"""

    collector_type = serializers.ChoiceField(choices=("kubernetes", "k3s"))
    monitor_object_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=200)
    instance_id = serializers.CharField(max_length=200)
    interval = serializers.IntegerField(required=False, min_value=1)


class K8sDaemonSetTolerationSerializer(OpenAPIRequestSerializer):
    """DaemonSet 容忍项。只声明 key、effect、value；服务层继续做 Kubernetes 名称校验。"""

    key = serializers.CharField()
    effect = serializers.ChoiceField(choices=("NoSchedule", "NoExecute"))
    value = serializers.CharField(required=False, allow_blank=True)


class MonitorClusterInstallCommandSerializer(OpenAPIRequestSerializer):
    """生成复制到集群执行的安装命令。collector_type=k3s 时同时返回卸载命令。"""

    collector_type = serializers.ChoiceField(choices=("kubernetes", "k3s"))
    instance_id = serializers.CharField(max_length=200)
    cloud_region_id = serializers.IntegerField(min_value=1)
    image_registry_prefix = serializers.CharField(required=False, allow_blank=True, max_length=200)
    tolerations = serializers.ListField(child=K8sDaemonSetTolerationSerializer(), required=False, max_length=16)

    def validate(self, attrs):
        if attrs["collector_type"] == "k3s" and ("image_registry_prefix" in self.initial_data or "tolerations" in self.initial_data):
            raise serializers.ValidationError("k3s 不接受镜像仓库前缀或容忍度")
        return attrs


class MonitorClusterStatusQuerySerializer(OpenAPIRequestSerializer):
    """检查 Kubernetes 或 K3s 采集是否已经上报。kubernetes 要带监控对象，k3s 不带。"""

    collector_type = serializers.ChoiceField(choices=("kubernetes", "k3s"))
    instance_id = serializers.CharField(max_length=200)
    monitor_object_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        if attrs["collector_type"] == "kubernetes" and not attrs.get("monitor_object_id"):
            raise serializers.ValidationError({"monitor_object_id": ["kubernetes 状态查询必须提供监控对象"]})
        if attrs["collector_type"] == "k3s" and "monitor_object_id" in self.initial_data:
            raise serializers.ValidationError({"monitor_object_id": ["k3s 状态查询不使用监控对象"]})
        return attrs
