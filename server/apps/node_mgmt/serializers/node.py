from rest_framework import serializers
from django.db.models import Prefetch
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.models.node_version import NodeComponentVersion
from apps.node_mgmt.utils.version_utils import VersionUtils


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
        """获取节点关联的控制器版本信息，包含升级提示"""
        # 如果 context 中没有 latest_versions_map，说明不需要返回版本信息
        latest_versions_map = self.context.get('latest_versions_map')
        if latest_versions_map is None:
            return []

        versions = []
        component_versions = [v for v in obj.component_versions.all() if v.component_type == 'controller']

        if not component_versions:
            return versions

        # 从 context 中获取最新版本映射（在视图层已经查询好了）
        os_latest_versions = latest_versions_map.get(obj.operating_system, {})

        # 构建版本信息，包含升级提示
        for version_info in component_versions:
            current_version = version_info.version
            latest_version = os_latest_versions.get(version_info.component_id, '')

            # 检查当前版本是否包含特殊标签
            current_is_latest = current_version and 'latest' in current_version.lower()
            current_is_unknown = current_version and 'unknown' in current_version.lower()
            latest_is_latest = latest_version and 'latest' in latest_version.lower()

            # 升级逻辑：
            # 1. 当前版本是 unknown → 不进行版本对比，不提示升级
            # 2. 当前版本是 latest → 不升级
            # 3. 当前版本不是 latest，最新版本是 latest → 需要升级
            # 4. 都是正常版本号 → 进行版本号比较
            if current_is_unknown:
                # 当前版本未知，不进行版本对比
                upgradeable = False
            elif current_is_latest:
                # 当前已经是 latest，不需要升级
                upgradeable = False
            elif latest_is_latest:
                # 最新版本是 latest，当前不是 latest → 需要升级
                upgradeable = True
            elif not latest_version:
                # 没有找到最新版本，无法判断
                upgradeable = False
            else:
                # 都是正常版本号，进行版本比较
                upgradeable = VersionUtils.is_upgradeable(current_version, latest_version)

            # 如果没有查到最新版本，使用当前版本
            if not latest_version:
                latest_version = current_version

            versions.append({
                'component_type': version_info.component_type,
                'component_id': version_info.component_id,
                'version': current_version,
                'latest_version': latest_version or 'unknown',
                'upgradeable': upgradeable,
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
