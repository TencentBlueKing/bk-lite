from rest_framework import serializers
from apps.node_mgmt.models.sidecar import Node


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = ['id', 'name', 'ip', 'operating_system', 'status', 'cloud_region']


class BatchBindingNodeConfigurationSerializer(serializers.Serializer):
    node_ids = serializers.ListField(
        child=serializers.CharField(),
        required=True
    )
    collector_configuration_id = serializers.CharField(required=True)


class BatchOperateNodeCollectorSerializer(serializers.Serializer):
    node_ids = serializers.ListField(
        child=serializers.CharField(),
        required=True
    )
    collector_id = serializers.CharField(required=True)
    operation = serializers.ChoiceField(choices=['start', 'restart', 'stop'], required=True)
