from rest_framework import serializers

from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Collector, CollectorConfiguration
from apps.node_mgmt.utils.permission import get_authorized_node_queryset


class CollectorConfigurationSerializer(serializers.ModelSerializer):
    collector = serializers.CharField(source='collector.id')
    collector_name = serializers.CharField(source='collector.name')
    nodes = serializers.SerializerMethodField()
    operating_system = serializers.CharField(source='collector.node_operating_system')

    def get_nodes(self, instance):
        authorized_node_ids = self.context.get("authorized_node_ids")
        if authorized_node_ids is None:
            request = self.context.get("request")
            authorized_node_ids = (
                frozenset(get_authorized_node_queryset(request).values_list("id", flat=True)) if request is not None else frozenset()
            )
            self.context["authorized_node_ids"] = authorized_node_ids
        return [node.id for node in instance.nodes.all() if node.id in authorized_node_ids]

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
