from rest_framework import serializers

from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.utils.proxy_address import normalize_proxy_address


def _validate_proxy_address(value, *, allow_blank=False):
    try:
        return normalize_proxy_address(value, allow_blank=allow_blank)
    except ValueError as exc:
        raise serializers.ValidationError(str(exc))


class CloudRegionServiceSerializer(serializers.ModelSerializer):
    """云区域服务序列化器"""
    deployment_status = serializers.SerializerMethodField()
    health_status = serializers.SerializerMethodField()

    class Meta:
        model = CloudRegionService
        fields = [
            "id",
            "name",
            "status",
            "description",
            "message",
            "deployment_status",
            "health_status",
        ]

    def get_deployment_status(self, instance):
        if instance.deployed_status == CloudRegionServiceConstants.DEPLOYED:
            return "deployed"
        return "not_deployed"

    def get_health_status(self, instance):
        if instance.deployed_status != CloudRegionServiceConstants.DEPLOYED:
            return "unknown"
        if instance.status == CloudRegionServiceConstants.NORMAL:
            return "normal"
        return "abnormal"

    def to_representation(self, instance):
        """自定义序列化输出：当 deployed_status=0 时，status 默认为 'not_deployed'"""
        data = super().to_representation(instance)

        # 如果服务未部署，且不属于默认云区域，则将状态设置为 'not_deployed'
        if (
            instance.deployed_status == CloudRegionServiceConstants.NOT_DEPLOYED_STATUS
            and instance.cloud_region.id
            != CloudRegionConstants.DEFAULT_CLOUD_REGION_ID
        ):
            data["status"] = CloudRegionServiceConstants.NOT_DEPLOYED

        return data


class CloudRegionSerializer(serializers.ModelSerializer):
    services = CloudRegionServiceSerializer(source='cloudregionservice_set', many=True, read_only=True)
    is_default = serializers.SerializerMethodField()
    deployment_state = serializers.SerializerMethodField()
    health_state = serializers.SerializerMethodField()
    
    class Meta:
        model = CloudRegion
        fields = [
            'id',
            'name',
            'introduction',
            'proxy_address',
            'pending_proxy_address',
            'pending_proxy_address_created_at',
            'is_default',
            'deployment_state',
            'health_state',
            'services',
        ]
        read_only_fields = [
            "pending_proxy_address",
            "pending_proxy_address_created_at",
        ]

    def validate_proxy_address(self, value):
        return _validate_proxy_address(value, allow_blank=True)

    def get_is_default(self, instance):
        return instance.is_default

    def get_deployment_state(self, instance):
        if self.get_is_default(instance):
            return "system_managed"

        services_by_name = {
            service.name: service
            for service in instance.cloudregionservice_set.all()
            if service.name in CloudRegionServiceConstants.SERVICES
        }
        deployed_count = sum(
            services_by_name.get(service_name) is not None
            and services_by_name[service_name].deployed_status
            == CloudRegionServiceConstants.DEPLOYED
            for service_name in CloudRegionServiceConstants.SERVICES
        )
        if deployed_count == 0:
            return "not_deployed"
        if deployed_count < len(CloudRegionServiceConstants.SERVICES):
            return "partially_deployed"
        return "deployed"

    def get_health_state(self, instance):
        services_by_name = {
            service.name: service
            for service in instance.cloudregionservice_set.all()
            if service.name in CloudRegionServiceConstants.SERVICES
        }
        if not any(
            service.deployed_status == CloudRegionServiceConstants.DEPLOYED
            for service in services_by_name.values()
        ):
            return "unknown"
        if all(
            services_by_name.get(service_name) is not None
            and services_by_name[service_name].deployed_status
            == CloudRegionServiceConstants.DEPLOYED
            and services_by_name[service_name].status
            == CloudRegionServiceConstants.NORMAL
            for service_name in CloudRegionServiceConstants.SERVICES
        ):
            return "normal"
        return "abnormal"


class CloudRegionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CloudRegion
        fields = ['name', 'introduction', 'proxy_address']

    def validate_proxy_address(self, value):
        return _validate_proxy_address(value, allow_blank=True)


class CloudRegionProxyAddressSerializer(serializers.Serializer):
    proxy_address = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_proxy_address(self, value):
        return _validate_proxy_address(value)


class CloudRegionProxyActivationSerializer(serializers.Serializer):
    confirmed = serializers.BooleanField()
