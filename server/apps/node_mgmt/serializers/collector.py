from rest_framework import serializers
from apps.node_mgmt.models.sidecar import Collector


class CollectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collector
        fields = "__all__"
