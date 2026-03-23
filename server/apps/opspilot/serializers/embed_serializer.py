from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.models import EmbedProvider
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class EmbedProviderSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.embed_model"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("vendor") and not getattr(self.instance, "vendor_id", None):
            raise serializers.ValidationError({"vendor": "供应商不能为空"})
        if not attrs.get("model") and not getattr(self.instance, "model", None):
            raise serializers.ValidationError({"model": "模型不能为空"})
        return attrs

    class Meta:
        model = EmbedProvider
        fields = "__all__"
