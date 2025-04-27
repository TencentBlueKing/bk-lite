from rest_framework import serializers

from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import CollectorConfiguration, Node, Collector


class CollectorConfigurationSerializer(serializers.ModelSerializer):
    collector = serializers.CharField(source='collector.id')
    collector_name = serializers.CharField(source='collector.name')
    nodes = serializers.PrimaryKeyRelatedField(queryset=Node.objects.all(), many=True)
    operating_system = serializers.CharField(source='collector.node_operating_system')

    class Meta:
        model = CollectorConfiguration
        fields = ['id', 'name', 'config_template', 'operating_system', 'collector', "collector_name", 'nodes']


class CollectorConfigurationCreateSerializer(serializers.ModelSerializer):
    cloud_region_id = serializers.PrimaryKeyRelatedField(queryset=CloudRegion.objects.all(), source='cloud_region')
    collector_id = serializers.PrimaryKeyRelatedField(queryset=Collector.objects.all(), source='collector')

    class Meta:
        model = CollectorConfiguration
        fields = ['name', 'config_template', 'collector_id', 'cloud_region_id']


class CollectorConfigurationUpdateSerializer(serializers.ModelSerializer):
    collector_id = serializers.PrimaryKeyRelatedField(queryset=Collector.objects.all(), source='collector')

    class Meta:
        model = CollectorConfiguration
        fields = ['name', 'config_template', 'collector_id']


class BulkDeleteConfigurationSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.CharField(),
        required=True
    )


class ApplyToNodeSerializer(serializers.Serializer):
    node_id = serializers.CharField(required=True)
    collector_configuration_id = serializers.CharField(required=True)
