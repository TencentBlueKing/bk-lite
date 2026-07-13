from rest_framework import serializers

from apps.cmdb.services.k8s_resource_overview import LAYER_LIMITS, RESOURCE_KINDS


class K8sPageQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=50, default=50)


class K8sLayerQuerySerializer(K8sPageQuerySerializer):
    namespace_ids = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_namespace_ids(self, value):
        if not value:
            return []
        try:
            return [int(item.strip()) for item in str(value).split(",") if item.strip()]
        except ValueError as exc:
            raise serializers.ValidationError("namespace_ids 必须是逗号分隔的整数") from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        layer = self.context.get("layer")
        if layer not in LAYER_LIMITS:
            raise serializers.ValidationError({"layer": f"不支持的拓扑层: {layer}"})
        if attrs["page_size"] > LAYER_LIMITS[layer]:
            raise serializers.ValidationError({"page_size": f"{layer} page_size 不能超过 {LAYER_LIMITS[layer]}"})
        if layer == "workload" and not attrs["namespace_ids"]:
            raise serializers.ValidationError({"namespace_ids": "Workload 分层查询必须提供已加载的 Namespace"})
        return attrs


class K8sResourceListQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=500, default=20)
    search = serializers.CharField(required=False, allow_blank=True, default="")
    order = serializers.ChoiceField(
        required=False,
        default="name",
        choices=[
            "name",
            "-name",
            "namespace",
            "-namespace",
            "workload_type",
            "-workload_type",
            "replicas",
            "-replicas",
        ],
    )
    namespace_id = serializers.IntegerField(required=False, min_value=1, allow_null=True, default=None)
    workload_id = serializers.IntegerField(required=False, min_value=1, allow_null=True, default=None)
    node_id = serializers.IntegerField(required=False, min_value=1, allow_null=True, default=None)


class K8sResourceKindSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=RESOURCE_KINDS)
