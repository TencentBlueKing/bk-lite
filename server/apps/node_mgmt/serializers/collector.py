from rest_framework import serializers
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class CollectorSerializer(serializers.ModelSerializer):
    def validate_cpu_architecture(self, value):
        return normalize_cpu_architecture(value)

    class Meta:
        model = Collector
        fields = "__all__"
