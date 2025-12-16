from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.cloud_region import SidecarEnv
from rest_framework import serializers


class SidecarEnvSerializer(serializers.ModelSerializer):
    class Meta:
        model = SidecarEnv
        fields = ['id', 'key', 'value', 'description', 'type']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.type == EnvVariableConstants.TYPE_SECRET:
            data['value'] = EnvVariableConstants.SECRET_MASK
        return data

    def create(self, validated_data):
        validated_data['value'] = self._encrypt_if_secret(validated_data['value'], validated_data['type'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'value' in validated_data:
            validated_data['value'] = self._encrypt_if_secret(
                validated_data['value'], validated_data.get('type', instance.type)
            )
        return super().update(instance, validated_data)

    def _encrypt_if_secret(self, value, type_):
        if type_ == EnvVariableConstants.TYPE_SECRET:
            aes_obj = AESCryptor()
            secret_value = aes_obj.encode(value)
            return secret_value
        return value


class EnvVariableCreateSerializer(serializers.ModelSerializer):
    cloud_region_id = serializers.PrimaryKeyRelatedField(queryset=CloudRegion.objects.all(), source='cloud_region')

    class Meta:
        model = SidecarEnv
        fields = ['key', 'value', 'type', 'description', 'cloud_region_id']


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
