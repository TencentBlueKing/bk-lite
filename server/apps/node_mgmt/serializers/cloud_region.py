from rest_framework import serializers

from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants


class CloudRegionServiceSerializer(serializers.ModelSerializer):
    """云区域服务序列化器"""
    class Meta:
        model = CloudRegionService
        fields = ['id', 'name', 'status', 'description']

    def to_representation(self, instance):
        """自定义序列化输出：当 deployed_status=0 时，status 默认为 'not_deployed'"""
        data = super().to_representation(instance)

        # 当部署状态为未部署时，status 默认为 'not_deployed'
        if instance.deployed_status == CloudRegionServiceConstants.NOT_DEPLOYED_STATUS and instance.cloud_region.id != CloudRegionConstants.DEFAULT_CLOUD_REGION_ID:
            data['status'] = CloudRegionServiceConstants.NOT_DEPLOYED

        return data


class CloudRegionSerializer(serializers.ModelSerializer):
    services = CloudRegionServiceSerializer(source='cloudregionservice_set', many=True, read_only=True)
    
    class Meta:
        model = CloudRegion
        fields = ['id', 'name', 'introduction', 'proxy_address', 'services']


class CloudRegionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudRegion
        fields = ['name', 'introduction', 'proxy_address']
