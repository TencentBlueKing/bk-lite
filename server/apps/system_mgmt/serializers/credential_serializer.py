from rest_framework import serializers

from apps.system_mgmt.models.credential import CredentialType
from apps.system_mgmt.services.credential_builtin import effective_type_fields


class CredentialTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CredentialType
        fields = ("key", "name", "is_builtin", "categories", "fields")
        read_only_fields = ("is_builtin",)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["fields"] = effective_type_fields(instance)
        return data


class CredentialSerializer(serializers.Serializer):
    credential_id = serializers.CharField(read_only=True)
    name = serializers.CharField(max_length=128)
    type = serializers.CharField(max_length=64)
    group_id = serializers.IntegerField()
    disabled = serializers.BooleanField(required=False)
    fields = serializers.DictField(required=False)

    def to_representation(self, instance):
        if isinstance(instance, dict):
            return dict(instance)
        from apps.system_mgmt.services.credential_service import _public_credential

        return _public_credential(instance)
