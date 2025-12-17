from rest_framework import serializers
from apps.node_mgmt.models.sidecar import Node


class NodeSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = ['id', 'name', 'ip', 'operating_system', 'status', 'cloud_region', 'updated_at', 'organization', 'install_method', 'node_type', 'versions']

    def get_organization(self, obj):
        return [rel.organization for rel in obj.nodeorganization_set.all()]

    def get_versions(self, obj):
        """获取节点关联的控制器版本信息"""
        versions = []
        for version_info in obj.component_versions.filter(component_type='controller'):
            versions.append({
                'component_type': version_info.component_type,
                'component_id': version_info.component_id,
                'version': version_info.version,
                'message': version_info.message,
                'last_check_at': version_info.last_check_at,
            })
        return versions


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
