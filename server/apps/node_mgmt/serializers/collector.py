from rest_framework import serializers
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture
from apps.node_mgmt.utils.collector_tags import normalize_collector_tags


class CollectorSerializer(serializers.ModelSerializer):
    def validate_cpu_architecture(self, value):
        return normalize_cpu_architecture(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs["tags"] = normalize_collector_tags(
            attrs.get("tags"),
            attrs.get("node_operating_system"),
            attrs.get("cpu_architecture"),
        )
        return attrs

    class Meta:
        model = Collector
        fields = "__all__"
