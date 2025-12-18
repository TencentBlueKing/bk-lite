from rest_framework import serializers
from django.db.models import Prefetch
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.models.node_version import NodeComponentVersion


class NodeSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    versions = serializers.SerializerMethodField()

    class Meta:
        model = Node
        fields = ['id', 'name', 'ip', 'operating_system', 'status', 'cloud_region', 'updated_at', 'organization', 'install_method', 'node_type', 'versions']

    @classmethod
    def setup_eager_loading(cls, queryset):
        """
        优化查询，预加载关联数据，避免 N+1 查询问题

        使用方法：
        queryset = NodeSerializer.setup_eager_loading(queryset)
        serializer = NodeSerializer(queryset, many=True)
        """
        queryset = queryset.prefetch_related(
            'nodeorganization_set',
            Prefetch(
                'component_versions',
                queryset=NodeComponentVersion.objects.filter(
                    component_type='controller'
                ).order_by('-last_check_at')
            )
        )
        return queryset

    def get_organization(self, obj):
        # 使用预加载的数据，不会触发额外查询
        return [rel.organization for rel in obj.nodeorganization_set.all()]

    def get_versions(self, obj):
        """获取节点关联的控制器版本信息（直接读取已计算好的升级状态）"""
        versions = []
        component_versions = [v for v in obj.component_versions.all() if v.component_type == 'controller']

        for version_info in component_versions:
            versions.append({
                'component_type': version_info.component_type,
                'component_id': version_info.component_id,
                'version': version_info.version,
                'latest_version': version_info.latest_version or 'unknown',
                'upgradeable': version_info.upgradeable,
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
