from rest_framework import serializers
from apps.node_mgmt.models.sidecar import ChildConfig


class ChildConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChildConfig
        fields = "__all__"
