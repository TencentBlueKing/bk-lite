from rest_framework import serializers
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService


class CloudRegionServiceSerializer(serializers.ModelSerializer):
    """云区域服务序列化器"""
    class Meta:
        model = CloudRegionService
        fields = ['id', 'name', 'status', 'description']


class CloudRegionSerializer(serializers.ModelSerializer):
    services = CloudRegionServiceSerializer(source='cloudregionservice_set', many=True, read_only=True)

    class Meta:
        model = CloudRegion
        fields = ['id', 'name', 'introduction', 'services']


class CloudRegionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudRegion
        fields = ['name', 'introduction']
