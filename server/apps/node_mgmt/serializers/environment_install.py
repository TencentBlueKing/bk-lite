import ipaddress

from rest_framework import serializers


class EnvironmentBundleRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField(min_value=1)
    package_id = serializers.IntegerField(min_value=1)
    organization = serializers.IntegerField(min_value=1)
    valid_days = serializers.IntegerField(min_value=1, max_value=30, default=7)
    max_nodes = serializers.IntegerField(min_value=1, max_value=10000)
    platform_ca = serializers.CharField(required=False, allow_blank=True, max_length=65536, default="")
    management_cidr = serializers.CharField(required=False, allow_blank=True, max_length=32, default="")
    required_collectors = serializers.ListField(child=serializers.CharField(max_length=100), max_length=20, required=False, default=list)
    required_free_bytes = serializers.IntegerField(min_value=128 * 1024 * 1024)
    timeout_seconds = serializers.IntegerField(min_value=30, max_value=3600, default=900)

    def validate_management_cidr(self, value):
        if value:
            try:
                return str(ipaddress.IPv4Network(value))
            except ValueError:
                raise serializers.ValidationError("A canonical IPv4 network is required")
        return value


class EnvironmentGrantIDSerializer(serializers.Serializer):
    grant_id = serializers.UUIDField()


class EnvironmentComponentOptionsSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField(min_value=1)


class EnvironmentGrantListSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField(min_value=1, required=False)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=10)


class EnvironmentResultListSerializer(EnvironmentGrantIDSerializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=10)
