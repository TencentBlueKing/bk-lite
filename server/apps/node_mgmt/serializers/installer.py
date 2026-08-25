from rest_framework import serializers

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.utils.winrm import default_winrm_port, winrm_profile_error


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
    port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    username = serializers.CharField(required=False, allow_blank=True, default="")
    password = serializers.CharField(required=False, allow_blank=True, default="")
    private_key = serializers.CharField(required=False, allow_blank=True, default="")
    passphrase = serializers.CharField(required=False, allow_blank=True, default="")
    node_id = serializers.CharField(required=False, allow_blank=True)
    winrm_scheme = serializers.ChoiceField(choices=("http", "https"), required=False, default="https")
    winrm_transport = serializers.ChoiceField(
        choices=("basic", "ntlm", "kerberos", "credssp"),
        required=False,
        default="ntlm",
    )
    winrm_cert_validation = serializers.BooleanField(required=False, default=False)


class ControllerInstallRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField()
    work_node = serializers.CharField()
    package_id = serializers.IntegerField()
    cpu_architecture = serializers.CharField(allow_blank=False)
    nodes = InstallNodeSerializer(many=True, allow_empty=False)
    push_targets = serializers.ListField(
        child=serializers.CharField(allow_blank=False),
        required=False,
        allow_empty=True,
        default=list,
    )

    def validate(self, attrs):
        node_operating_systems = {
            node.get("os") or NodeConstants.LINUX_OS for node in attrs["nodes"]
        }
        if len(node_operating_systems) != 1:
            raise serializers.ValidationError({"nodes": "A controller installation batch must use one operating system"})
        target_os = node_operating_systems.pop()
        InstallerService.validate_controller_package_os(attrs["package_id"], target_os)
        normalized_arch = InstallerService.normalize_required_cpu_architecture(
            target_os,
            attrs["cpu_architecture"],
        )
        attrs["cpu_architecture"] = normalized_arch
        normalized_nodes = []
        for node in attrs["nodes"]:
            node_os = node.get("os") or NodeConstants.LINUX_OS
            if node_os == NodeConstants.WINDOWS_OS:
                node.setdefault("port", default_winrm_port(node.get("winrm_scheme") or "https"))
            else:
                node.setdefault("port", 22)
            if not node.get("username"):
                raise serializers.ValidationError({"nodes": "Remote installation requires a username"})
            if node_os == NodeConstants.WINDOWS_OS:
                if not node.get("password"):
                    raise serializers.ValidationError({"nodes": "Windows remote installation requires a password"})
                profile_error = winrm_profile_error(
                    node.get("winrm_scheme") or "https",
                    node["port"],
                    node.get("winrm_transport") or "ntlm",
                )
                if profile_error:
                    raise serializers.ValidationError({"nodes": profile_error})
                if node.get("winrm_scheme") == "http":
                    node["winrm_cert_validation"] = False
            node["os"] = node_os
            node["cpu_architecture"] = InstallerService.normalize_required_cpu_architecture(
                node_os,
                node.get("cpu_architecture") or normalized_arch,
            )
            normalized_nodes.append(node)
        attrs["nodes"] = normalized_nodes
        return attrs


class ControllerRetryRequestSerializer(serializers.Serializer):
    task_id = serializers.IntegerField(min_value=1)
    task_node_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
    port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    username = serializers.CharField(required=False, allow_blank=False, max_length=100)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    private_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    passphrase = serializers.CharField(required=False, allow_blank=True, write_only=True)
    winrm_scheme = serializers.ChoiceField(choices=("http", "https"), required=False)
    winrm_transport = serializers.ChoiceField(choices=("ntlm",), required=False)
    winrm_cert_validation = serializers.BooleanField(required=False)

    def validate(self, attrs):
        scheme = attrs.get("winrm_scheme")
        port = attrs.get("port")
        transport = attrs.get("winrm_transport") or "ntlm"
        if scheme and port is not None:
            profile_error = winrm_profile_error(scheme, port, transport)
            if profile_error:
                raise serializers.ValidationError(profile_error)
        if scheme == "http":
            attrs["winrm_cert_validation"] = False
        return attrs


class ControllerUninstallNodeSerializer(serializers.Serializer):
    node_id = serializers.CharField(allow_blank=False)
    ip = serializers.CharField()
    node_name = serializers.CharField(required=False, allow_blank=True, default="")
    os = serializers.ChoiceField(choices=(NodeConstants.LINUX_OS, NodeConstants.WINDOWS_OS))
    organizations = serializers.ListField(
        child=CanonicalOrganizationIdField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    port = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    username = serializers.CharField(allow_blank=False, max_length=100)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    private_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    passphrase = serializers.CharField(required=False, allow_blank=True, write_only=True)
    winrm_scheme = serializers.ChoiceField(choices=("http", "https"), required=False, default="https")
    winrm_transport = serializers.ChoiceField(
        choices=("basic", "ntlm", "kerberos", "credssp"),
        required=False,
        default="ntlm",
    )
    winrm_cert_validation = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        is_windows = attrs["os"] == NodeConstants.WINDOWS_OS
        if is_windows:
            attrs.setdefault("port", default_winrm_port(attrs.get("winrm_scheme") or "https"))
        else:
            attrs.setdefault("port", 22)
        if is_windows:
            if not attrs.get("password"):
                raise serializers.ValidationError("Windows controller uninstallation requires a password")
            profile_error = winrm_profile_error(
                attrs.get("winrm_scheme") or "https",
                attrs["port"],
                attrs.get("winrm_transport") or "ntlm",
            )
            if profile_error:
                raise serializers.ValidationError(profile_error)
            if attrs.get("winrm_scheme") == "http":
                attrs["winrm_cert_validation"] = False
        elif not attrs.get("password") and not attrs.get("private_key"):
            raise serializers.ValidationError("Linux controller uninstallation requires a password or private key")
        return attrs


class ControllerUninstallRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField(min_value=1)
    work_node = serializers.CharField(allow_blank=False)
    nodes = ControllerUninstallNodeSerializer(many=True, allow_empty=False)


class ControllerManualInstallRequestSerializer(serializers.Serializer):
    cloud_region_id = serializers.IntegerField()
    os = serializers.CharField()
    cpu_architecture = serializers.CharField(allow_blank=False)
    package_id = serializers.IntegerField()
    nodes = InstallNodeSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        InstallerService.validate_controller_package_os(attrs["package_id"], attrs["os"])
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
