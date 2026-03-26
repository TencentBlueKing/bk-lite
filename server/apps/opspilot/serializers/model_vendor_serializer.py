from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.serializers import TeamSerializer
from apps.opspilot.models.model_provider_mgmt import ModelVendor


class CustomProviderSerializer(TeamSerializer):
    vendor_name = serializers.SerializerMethodField()
    vendor_type = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        vendor_list = ModelVendor.objects.all().values("id", "name", "vendor_type")
        self.vendor_map = {item["id"]: {"name": item["name"], "vendor_type": item["vendor_type"]} for item in vendor_list}

    def get_fields(self):
        return super().get_fields()

    def get_vendor_name(self, instance):
        if getattr(instance, "vendor_id", None):
            return self.vendor_map.get(instance.vendor_id, {}).get("name", "")
        return ""

    def get_vendor_type(self, instance):
        if getattr(instance, "vendor_id", None):
            return self.vendor_map.get(instance.vendor_id, {}).get("vendor_type", "")
        return ""


class ModelVendorSerializer(serializers.ModelSerializer):
    # 读取时返回脱敏值
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = ModelVendor
        fields = [
            "id",
            "name",
            "vendor_type",
            "api_base",
            "api_key",
            "enabled",
            "team",
            "description",
            "is_build_in",
        ]

    def get_api_key_display(self, instance):
        # 返回脱敏值，避免被抓包泄露
        return "******" if instance.api_key else ""

    def update(self, instance, validated_data):
        # 前端更新时可能不传 api_key，此时跳过更新，保留原值
        api_key = validated_data.get("api_key")
        if not api_key:
            validated_data.pop("api_key", None)
        return super().update(instance, validated_data)


class ModelVendorTestConnectionSerializer(serializers.Serializer):
    original_id = serializers.IntegerField(required=False, allow_null=True)
    api_base = serializers.CharField(required=True, allow_blank=False)
    api_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password_changed = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        password_changed = attrs.get("password_changed", True)
        api_key = attrs.get("api_key") or ""
        original_id = attrs.get("original_id")

        if password_changed:
            if not api_key:
                raise serializers.ValidationError({"api_key": "API Key 不能为空"})
            attrs["resolved_api_key"] = api_key
            return attrs

        if not original_id:
            raise serializers.ValidationError({"original_id": "未修改密码时，原供应商ID不能为空"})

        vendor = ModelVendor.objects.filter(id=original_id).first()
        if not vendor:
            raise serializers.ValidationError({"original_id": "原供应商不存在"})

        attrs["resolved_api_key"] = vendor.decrypted_api_key
        return attrs
