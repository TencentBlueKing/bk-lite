from rest_framework import serializers

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.services.installer import InstallerService


class CanonicalOrganizationIdField(serializers.Field):
    default_error_messages = {"invalid": "组织 ID 必须是规范正整数"}

    def to_internal_value(self, data):
        try:
            return next(iter(_normalize_organization_ids([data])))
        except BaseAppException:
            self.fail("invalid")

    def to_representation(self, value):
        return int(value)


class InstallNodeSerializer(serializers.Serializer):
    ip = serializers.CharField()
    node_name = serializers.CharField(required=False, allow_blank=True, default="")
    os = serializers.CharField(required=False, allow_blank=True)
    cpu_architecture = serializers.CharField(required=False, allow_blank=True, default="")
    organizations = serializers.ListField(
        child=CanonicalOrganizationIdField(),
        required=True,
        allow_empty=False,
    )
    port = serializers.IntegerField(required=False)
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, default="")
    private_key = serializers.CharField(required=False, allow_blank=True, default="")
    passphrase = serializers.CharField(required=False, allow_blank=True, default="")
    node_id = serializers.CharField(required=False, allow_blank=True)


class ControllerInstallRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField()
    work_node = serializers.CharField()
    package_id = serializers.IntegerField()
    cpu_architecture = serializers.CharField(allow_blank=False)
    nodes = InstallNodeSerializer(many=True)

    def validate(self, attrs):
        normalized_arch = InstallerService.normalize_required_cpu_architecture(
            attrs["nodes"][0].get("os", NodeConstants.LINUX_OS),
            attrs["cpu_architecture"],
        )
        attrs["cpu_architecture"] = normalized_arch
        normalized_nodes = []
        for node in attrs["nodes"]:
            node_os = node.get("os") or NodeConstants.LINUX_OS
            node["os"] = node_os
            node["cpu_architecture"] = InstallerService.normalize_required_cpu_architecture(
                node_os,
                node.get("cpu_architecture") or normalized_arch,
            )
            normalized_nodes.append(node)
        attrs["nodes"] = normalized_nodes
        return attrs


class ControllerManualInstallRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField()
    os = serializers.CharField()
    cpu_architecture = serializers.CharField(allow_blank=False)
    package_id = serializers.IntegerField()
    nodes = InstallNodeSerializer(many=True)

    def validate(self, attrs):
        attrs["cpu_architecture"] = InstallerService.normalize_required_cpu_architecture(
            attrs["os"],
            attrs["cpu_architecture"],
        )
        return attrs


class InstallCommandRequestSerializer(serializers.Serializer):
    ip = serializers.CharField()
    node_id = serializers.CharField()
    os = serializers.CharField()
    cpu_architecture = serializers.CharField(allow_blank=False)
    package_id = serializers.IntegerField()
    cloud_region_id = serializers.IntegerField()
    organizations = serializers.ListField(
        child=CanonicalOrganizationIdField(),
        required=True,
        allow_empty=False,
    )
    node_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        attrs["cpu_architecture"] = InstallerService.normalize_required_cpu_architecture(
            attrs["os"],
            attrs["cpu_architecture"],
        )
        return attrs


class InstallerArtifactQuerySerializer(serializers.Serializer):
    arch = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        target_os = self.context.get("target_os") or NodeConstants.LINUX_OS
        arch = attrs.get("arch")
        if arch:
            attrs["arch"] = InstallerService.normalize_required_cpu_architecture(target_os, arch)
        return attrs
