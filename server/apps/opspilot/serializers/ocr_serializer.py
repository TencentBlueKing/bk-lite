from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.opspilot.models import OCRProvider
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class OCRProviderSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.ocr_model"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("vendor") and not getattr(self.instance, "vendor_id", None):
            raise serializers.ValidationError({"vendor": "供应商不能为空"})
        vendor = attrs.get("vendor") or getattr(self.instance, "vendor", None)
        model = attrs.get("model", getattr(self.instance, "model", None))
        if vendor and getattr(vendor, "vendor_type", "") != "azure" and not model:
            raise serializers.ValidationError({"model": "非 Azure OCR 模型不能为空"})
        return attrs

    class Meta:
        model = OCRProvider
        fields = "__all__"

    def create(self, validated_data):
        validated_data["is_build_in"] = False
        return super().create(validated_data)
