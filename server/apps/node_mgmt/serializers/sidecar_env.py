from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.cloud_region import SidecarEnv
from apps.node_mgmt.services.installer_credentials import normalize_installer_credentials_mode
from rest_framework import serializers


class InstallerCredentialsModeValidationMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        key = attrs.get("key", getattr(self.instance, "key", None))
        if key != NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY:
            return attrs

        value = attrs.get("value", getattr(self.instance, "value", None))
        try:
            attrs["value"] = normalize_installer_credentials_mode(value)
        except ValueError as exc:
            raise serializers.ValidationError({"value": str(exc)})
        return attrs


class SidecarEnvSerializer(InstallerCredentialsModeValidationMixin, serializers.ModelSerializer):
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
        if type_ == EnvVariableConstants.TYPE_SECRET and value:
            aes_obj = AESCryptor()
            secret_value = aes_obj.encode(value)
            return secret_value
        return value


class EnvVariableCreateSerializer(InstallerCredentialsModeValidationMixin, serializers.ModelSerializer):
    cloud_region_id = serializers.PrimaryKeyRelatedField(queryset=CloudRegion.objects.all(), source='cloud_region')

    class Meta:
        model = SidecarEnv
        fields = ['key', 'value', 'type', 'description', 'cloud_region_id']

    def create(self, validated_data):
        # 如果是 secret 类型且值不为空，需要加密
        if validated_data.get('type') == EnvVariableConstants.TYPE_SECRET and validated_data.get('value'):
            aes_obj = AESCryptor()
            validated_data['value'] = aes_obj.encode(validated_data['value'])
        return super().create(validated_data)


class EnvVariableUpdateSerializer(InstallerCredentialsModeValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = SidecarEnv
        fields = ['key', 'value', 'description']


class BulkDeleteEnvVariableSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        help_text="需要删除的环境变量ID列表"
    )
