from rest_framework import serializers

from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.cloud_region import SidecarEnv


class SidecarEnvSerializer(serializers.ModelSerializer):
    class Meta:
        model = SidecarEnv
        fields = ['id', 'key', 'value', 'description']


class EnvVariableCreateSerializer(serializers.ModelSerializer):
    cloud_region_id = serializers.PrimaryKeyRelatedField(queryset=CloudRegion.objects.all(), source='cloud_region')

    class Meta:
        model = SidecarEnv
        fields = ['key', 'value', 'description', 'cloud_region_id']


class EnvVariableUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SidecarEnv
        fields = ['key', 'value', 'description']


class BulkDeleteEnvVariableSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        help_text="需要删除的环境变量ID列表"
    )
