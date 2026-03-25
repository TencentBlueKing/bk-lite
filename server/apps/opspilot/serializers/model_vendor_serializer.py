from rest_framework import serializers
from rest_framework.fields import empty

from apps.opspilot.models.model_provider_mgmt import ModelVendor


class CustomProviderSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = ModelVendor
        fields = [
            "id",
            "name",
            "vendor_type",
            "api_base",
            "enabled",
            "team",
            "description",
            "is_build_in",
        ]
        extra_kwargs = {"api_key": {"write_only": True}}
