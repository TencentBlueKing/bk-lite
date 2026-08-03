"""目标管理序列化器"""

from functools import cached_property
from pathlib import PurePosixPath

from rest_framework import serializers

from apps.core.mixinx import EncryptMixin
from apps.core.utils.serializers import TeamSerializer
from apps.job_mgmt.constants import WinRMTransport
from apps.job_mgmt.models import Target
from apps.job_mgmt.serializers.validators import validate_manual_credentials
from apps.node_mgmt.models import CloudRegion


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

    def validate(self, attrs):
        """验证凭据字段"""
        if self.instance:
            effective_attrs = dict(attrs)
            for field in (
                "os_type",
                "credential_source",
                "credential_id",
                "ssh_user",
                "ssh_credential_type",
                "ssh_password",
                "ssh_key_file",
                "winrm_user",
                "winrm_password",
                "cloud_region_id",
            ):
                if not effective_attrs.get(field):
                    effective_attrs[field] = getattr(self.instance, field, None)
            validate_manual_credentials(effective_attrs, require_cloud_region=True)
            return attrs
        return validate_manual_credentials(attrs, require_cloud_region=True)

    def validate_team(self, value):
        """确保 team 是列表"""
        if value is None:
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            return value
        raise serializers.ValidationError("team 必须是列表或整数")

    def create(self, validated_data):
        """创建时加密密码字段"""
        EncryptMixin.encrypt_field("ssh_password", validated_data)
        EncryptMixin.encrypt_field("ssh_key_passphrase", validated_data)
        EncryptMixin.encrypt_field("winrm_password", validated_data)
        validated_data.setdefault("winrm_cert_validation", False)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """只替换显式提交的新凭据，空值表示继续使用已保存凭据。"""
        for field in ("ssh_password", "ssh_key_passphrase", "winrm_password"):
            if field in validated_data and not validated_data[field]:
                validated_data.pop(field)
            else:
                EncryptMixin.encrypt_field(field, validated_data)

        next_credential_type = validated_data.get("ssh_credential_type", instance.ssh_credential_type)
        if next_credential_type == "password" and validated_data.get("ssh_password"):
            if instance.ssh_key_file:
                instance.ssh_key_file.delete(save=False)
            validated_data["ssh_key_file"] = None
            validated_data["ssh_key_passphrase"] = ""
        elif next_credential_type == "key" and validated_data.get("ssh_key_file"):
            validated_data["ssh_password"] = ""
        return super().update(instance, validated_data)

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


class TargetBatchDeleteSerializer(serializers.Serializer):
    """批量删除序列化器"""

    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class TargetTestConnectionSerializer(serializers.Serializer):
    """测试连接序列化器"""

    ip = serializers.IPAddressField(required=True)
    os_type = serializers.CharField(required=False, default="linux")
    cloud_region_id = serializers.IntegerField(required=True)
    driver = serializers.CharField(required=False, default="ansible")
    credential_source = serializers.CharField(required=False, default="manual")
    credential_id = serializers.CharField(required=False, allow_blank=True, default="")
    # SSH (Linux)
    ssh_port = serializers.IntegerField(required=False, default=22)
    ssh_user = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_credential_type = serializers.CharField(required=False, default="password")
    ssh_password = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_passphrase = serializers.CharField(required=False, allow_blank=True, default="")
    ssh_key_file = serializers.FileField(required=False, allow_null=True)
    # WinRM (Windows)
    winrm_port = serializers.IntegerField(required=False, default=5986)
    winrm_scheme = serializers.CharField(required=False, default="https")
    winrm_transport = serializers.ChoiceField(required=False, choices=WinRMTransport.CHOICES, default=WinRMTransport.NTLM)
    winrm_user = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_password = serializers.CharField(required=False, allow_blank=True, default="")
    winrm_cert_validation = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        """验证测试连接参数"""
        saved_target = self.context.get("saved_target")
        if not saved_target:
            # cloud_region_id 已通过字段 required=True 校验，这里不再重复
            return validate_manual_credentials(attrs, require_cloud_region=False)

        effective_attrs = dict(attrs)
        for field in (
            "credential_source",
            "credential_id",
            "ssh_user",
            "ssh_credential_type",
            "ssh_password",
            "ssh_key_file",
            "winrm_user",
            "winrm_password",
        ):
            if not effective_attrs.get(field):
                effective_attrs[field] = getattr(saved_target, field, None)
        validate_manual_credentials(effective_attrs, require_cloud_region=False)
        return attrs
