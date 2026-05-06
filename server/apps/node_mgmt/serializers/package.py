from rest_framework import serializers

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class PackageVersionSerializer(serializers.ModelSerializer):
    cpu_architecture = serializers.SerializerMethodField()

    class Meta:
        model = PackageVersion
        fields = "__all__"

    def get_cpu_architecture(self, obj):
        normalized_arch = normalize_cpu_architecture(getattr(obj, "cpu_architecture", ""))
        if normalized_arch:
            return normalized_arch
        if getattr(obj, "os", "") == NodeConstants.WINDOWS_OS and getattr(obj, "object", "") == "Controller":
            return NodeConstants.X86_64_ARCH
        return getattr(obj, "cpu_architecture", "")
