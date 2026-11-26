"""目标管理序列化器"""

from functools import cached_property
from pathlib import PurePosixPath

from django.db import transaction
from rest_framework import serializers

from apps.core.mixinx import EncryptMixin
from apps.core.utils.serializers import TeamSerializer
from apps.job_mgmt.constants import CredentialSource, ExecutorDriver, OSType, SSHCredentialType, WinRMScheme, WinRMTransport
from apps.job_mgmt.models import Target
from apps.job_mgmt.serializers.validators import validate_manual_credentials
from apps.job_mgmt.services.resource_organizations import organization_ids
from apps.job_mgmt.services.target_vault import describe_target_credential, describe_target_credentials, request_credential_actor
from apps.job_mgmt.utils.i18n import serializer_message
from apps.node_mgmt.models import CloudRegion

_LOCAL_LOGIN = ("ssh_user", "ssh_password", "ssh_key_passphrase", "ssh_key_file", "winrm_user", "winrm_password")
_SECRET_FIELDS = ("ssh_password", "ssh_key_passphrase", "winrm_password", "ssh_key_file")
_CONNECTION_FIELDS = (
    "ip",
    "cloud_region_id",
    "os_type",
    "credential_source",
    "credential_id",
    "driver",
    "ssh_port",
    "ssh_credential_type",
    "winrm_port",
    "winrm_scheme",
    "winrm_transport",
    "winrm_cert_validation",
)


def _delete_unreferenced_key(key_file):
    if not Target.objects.filter(ssh_key_file=key_file.name).exists():
        key_file.storage.delete(key_file.name)


def _connection_values(attrs, saved):
    values = dict(attrs)
    if saved is None:
        return values
    for key in _CONNECTION_FIELDS:
        values.setdefault(key, getattr(saved, key))
    if values["credential_source"] == saved.credential_source == CredentialSource.MANUAL and values["os_type"] == saved.os_type:
        for key in _LOCAL_LOGIN:
            if key not in values or (key in _SECRET_FIELDS and not values[key]):
                values[key] = getattr(saved, key)
    return values


class TargetSerializer(TeamSerializer):
    """目标序列化器"""

    os_type_display = serializers.CharField(source="get_os_type_display", read_only=True)
    driver_display = serializers.CharField(source="get_driver_display", read_only=True)
    credential_source_display = serializers.CharField(source="get_credential_source_display", read_only=True)
    ssh_credential_type_display = serializers.CharField(source="get_ssh_credential_type_display", read_only=True)
    winrm_scheme_display = serializers.CharField(source="get_winrm_scheme_display", read_only=True)
    cloud_region_name = serializers.SerializerMethodField()
    # 写入字段（创建/更新时使用）
    ssh_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    ssh_key_passphrase = serializers.CharField(write_only=True, required=False, allow_blank=True)
    winrm_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    ssh_key_file = serializers.FileField(
        write_only=True,
        required=False,
        allow_null=True,
        use_url=False,
    )
    has_ssh_password = serializers.SerializerMethodField()
    has_winrm_password = serializers.SerializerMethodField()
    has_ssh_key = serializers.SerializerMethodField()
    ssh_key_file_name = serializers.SerializerMethodField()

    @cached_property
    def cloud_region_map(self):
        """云区域 ID → 名称的映射；首次访问时一次性加载，单实例缓存。

        相较旧实现在 ``__init__`` 中无条件全表加载，仅在序列化时按需读取，
        校验未调用 ``to_representation`` 的场景（如内部批量 ``is_valid``）零开销。
        """
        return {cr["id"]: cr["name"] for cr in CloudRegion.objects.all().values("id", "name")}

    def get_cloud_region_name(self, instance):
        """获取云区域名称"""
        if instance.cloud_region_id:
            return self.cloud_region_map.get(instance.cloud_region_id)
        return None

    def get_has_ssh_password(self, instance):
        return bool(instance.ssh_password)

    def get_has_winrm_password(self, instance):
        return bool(instance.winrm_password)

    def get_has_ssh_key(self, instance):
        return bool(instance.ssh_key_file)

    def get_ssh_key_file_name(self, instance):
        if not instance.ssh_key_file:
            return ""
        return PurePosixPath(instance.ssh_key_file.name).name

    @cached_property
    def credential_descriptions(self):
        instances = self._iter_instances(self.instance)
        ids = {target.credential_id for target in instances if target.credential_source == CredentialSource.CREDENTIAL and target.credential_id}
        if not ids:
            return {}
        actor = request_credential_actor(self.context["request"])
        try:
            if isinstance(self.instance, Target):
                target = self.instance
                return {target.credential_id: describe_target_credential(target.credential_id, target.os_type, actor)}
            return describe_target_credentials(ids, actor)
        except ValueError:
            return {}

    def get_team_name(self, instance):
        return [self.group_map[pk] for pk in organization_ids(instance.team) if pk in self.group_map]

    def to_representation(self, instance):
        result = super().to_representation(instance)
        result["team"] = organization_ids(instance.team)
        name, available = "", None
        if instance.credential_source == CredentialSource.CREDENTIAL:
            detail = self.credential_descriptions.get(instance.credential_id)
            expected = "ssh" if instance.os_type == OSType.LINUX else "winrm"
            available = bool(detail and detail.get("type") == expected and not detail.get("disabled"))
            if detail:
                name = detail.get("name", "")
            result.update(ssh_user="", winrm_user="", ssh_key_file_name="", has_ssh_password=False, has_winrm_password=False, has_ssh_key=False)
        result.update(credential_name=name, credential_available=available)
        return result

    def validate(self, attrs):
        effective = _connection_values(attrs, self.instance)
        validate_manual_credentials(effective, require_cloud_region=True, serializer=self)
        if effective.get("credential_source") == CredentialSource.CREDENTIAL:
            credential_id = effective["credential_id"]
            try:
                detail = describe_target_credential(
                    credential_id, effective.get("os_type", OSType.LINUX), request_credential_actor(self.context["request"])
                )
            except ValueError as exc:
                raise serializers.ValidationError({"credential_id": str(exc)}) from exc
            if detail["disabled"]:
                raise serializers.ValidationError({"credential_id": serializer_message(self, "error.credential_disabled", "Credential disabled")})
            self.credential_descriptions = {credential_id: detail}
            for key in _LOCAL_LOGIN:
                attrs[key] = None if key == "ssh_key_file" else ""
            attrs["ssh_credential_type"] = SSHCredentialType.PASSWORD
        else:
            attrs["credential_id"] = ""
        return attrs

    def validate_team(self, value):
        """确保 team 是列表"""
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return value
        raise serializers.ValidationError(serializer_message(self, "error.team_must_be_list_or_int", "team must be a list or an integer"))

    def create(self, validated_data):
        """创建时加密密码字段"""
        EncryptMixin.encrypt_field("ssh_password", validated_data)
        EncryptMixin.encrypt_field("ssh_key_passphrase", validated_data)
        EncryptMixin.encrypt_field("winrm_password", validated_data)
        validated_data.setdefault("winrm_cert_validation", False)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """只替换显式提交的新凭据，空值表示继续使用已保存凭据。"""
        vault = validated_data.get("credential_source", instance.credential_source) == CredentialSource.CREDENTIAL
        switching_to_manual = not vault and instance.credential_source == CredentialSource.CREDENTIAL
        if switching_to_manual:
            for key in _LOCAL_LOGIN:
                validated_data.setdefault(key, None if key == "ssh_key_file" else "")
        if not vault:
            for field in ("ssh_password", "ssh_key_passphrase", "winrm_password"):
                if not switching_to_manual and field in validated_data and not validated_data[field]:
                    validated_data.pop(field)
                else:
                    EncryptMixin.encrypt_field(field, validated_data)

        next_type = validated_data.get("ssh_credential_type", instance.ssh_credential_type)
        if vault or (next_type == SSHCredentialType.PASSWORD and validated_data.get("ssh_password")):
            validated_data["ssh_key_file"] = None
            validated_data["ssh_key_passphrase"] = ""
        elif next_type == SSHCredentialType.KEY and validated_data.get("ssh_key_file"):
            validated_data["ssh_password"] = ""
            validated_data.setdefault("ssh_key_passphrase", "")

        old_key = instance.ssh_key_file
        with transaction.atomic():
            current = (
                Target.objects.select_for_update().filter(pk=instance.pk).values_list("updated_at", "credential_source", "credential_id").first()
            )
            if current != (instance.updated_at, instance.credential_source, instance.credential_id):
                raise serializers.ValidationError(serializer_message(self, "error.target_changed", "Target changed. Refresh and retry."))
            updated = super().update(instance, validated_data)
            if old_key and old_key.name != updated.ssh_key_file.name:
                transaction.on_commit(lambda: _delete_unreferenced_key(old_key))
        return updated

    class Meta:
        model = Target
        fields = [
            "id",
            "name",
            "ip",
            "os_type",
            "os_type_display",
            "cloud_region_id",
            "cloud_region_name",
            "node_id",
            "driver",
            "driver_display",
            "credential_source",
            "credential_source_display",
            "credential_id",
            "ssh_port",
            "ssh_user",
            "ssh_credential_type",
            "ssh_credential_type_display",
            "ssh_password",
            "ssh_key_passphrase",
            "ssh_key_file",
            "has_ssh_password",
            "has_ssh_key",
            "ssh_key_file_name",
            "winrm_port",
            "winrm_scheme",
            "winrm_scheme_display",
            "winrm_transport",
            "winrm_user",
            "winrm_password",
            "has_winrm_password",
            "winrm_cert_validation",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_by", "updated_at"]


class TargetTestConnectionSerializer(serializers.Serializer):
    """测试连接序列化器"""

    ip = serializers.IPAddressField(required=True)
    os_type = serializers.ChoiceField(required=False, choices=OSType.CHOICES, default=OSType.LINUX)
    cloud_region_id = serializers.IntegerField(required=True)
    driver = serializers.ChoiceField(required=False, choices=ExecutorDriver.CHOICES, default=ExecutorDriver.ANSIBLE)
    credential_source = serializers.ChoiceField(required=False, choices=CredentialSource.CHOICES, default=CredentialSource.MANUAL)
    credential_id = serializers.CharField(required=False, max_length=64, allow_blank=True, default="")
    # SSH (Linux)
    ssh_port = serializers.IntegerField(required=False, default=22)
    ssh_user = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_credential_type = serializers.ChoiceField(required=False, choices=SSHCredentialType.CHOICES, default=SSHCredentialType.PASSWORD)
    ssh_password = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_passphrase = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_file = serializers.FileField(required=False, allow_null=True)
    # WinRM (Windows)
    winrm_port = serializers.IntegerField(required=False, default=5986)
    winrm_scheme = serializers.ChoiceField(required=False, choices=WinRMScheme.CHOICES, default=WinRMScheme.HTTPS)
    winrm_transport = serializers.ChoiceField(required=False, choices=WinRMTransport.CHOICES, default=WinRMTransport.NTLM)
    winrm_user = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_password = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_cert_validation = serializers.BooleanField(required=False, default=True)

    def changes_connection(self, target):
        for key, value in self.validated_data.items():
            if key in _SECRET_FIELDS:
                if value:
                    return True
            elif value != getattr(target, key):
                return True
        return False

    def validate(self, attrs):
        """验证测试连接参数"""
        saved = self.context.get("saved_target")
        effective = _connection_values(attrs, saved)
        validate_manual_credentials(effective, require_cloud_region=True, serializer=self)
        if saved:
            for key in _CONNECTION_FIELDS + ("ssh_user", "winrm_user"):
                if key in effective:
                    attrs.setdefault(key, effective[key])
        return attrs
