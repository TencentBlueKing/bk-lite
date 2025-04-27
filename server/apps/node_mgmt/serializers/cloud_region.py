from rest_framework import serializers
from apps.node_mgmt.models.cloud_region import CloudRegion


class CloudRegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudRegion
        fields = ['id', 'name', 'introduction']


class CloudRegionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudRegion
        fields = ['introduction']
