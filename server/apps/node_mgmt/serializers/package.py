from rest_framework import serializers

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class PackageVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageVersion
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "type",
            "os",
            "cpu_architecture",
            "object",
            "version",
            "name",
            "description",
        ]

    @staticmethod
    def _normalized_cpu_architecture(obj):
        normalized_arch = normalize_cpu_architecture(getattr(obj, "cpu_architecture", ""))
        if normalized_arch:
            return normalized_arch
        if getattr(obj, "type", "") == "controller" and getattr(obj, "object", "") == "Controller":
            return NodeConstants.X86_64_ARCH
        if getattr(obj, "os", "") == NodeConstants.WINDOWS_OS and getattr(obj, "object", "") == "Controller":
            return NodeConstants.X86_64_ARCH
        return getattr(obj, "cpu_architecture", "")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["cpu_architecture"] = self._normalized_cpu_architecture(instance)
        return data
