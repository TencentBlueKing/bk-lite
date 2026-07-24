"""补丁源序列化器"""

from rest_framework import serializers

from apps.core.mixinx import EncryptMixin
from apps.core.utils.serializers import TeamSerializer
from apps.patch_mgmt.constants import PatchSourceType
from apps.patch_mgmt.models import PatchSource


# MVP 阶段支持的补丁源类型
MVP_SOURCE_TYPES = {
    PatchSourceType.WSUS,
    PatchSourceType.YUM_REPO,
    PatchSourceType.DNF_REPO,
    PatchSourceType.APT_REPO,
}


class PatchSourceConnectivitySerializer(serializers.Serializer):
    """校验尚未保存的补丁源连接参数。"""

    source_type = serializers.ChoiceField(choices=tuple(MVP_SOURCE_TYPES))
    url = serializers.CharField(max_length=512)
    distro_name = serializers.CharField(required=False, allow_blank=True, default="")
    os_version = serializers.CharField(required=False, allow_blank=True, default="")
    arch = serializers.CharField(required=False, allow_blank=True, default="")
    proxy_host = serializers.CharField(required=False, allow_blank=True, default="")
    proxy_port = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=65535)
    auth_user = serializers.CharField(required=False, allow_blank=True, default="")
    auth_password = serializers.CharField(required=False, allow_blank=True, default="")


def infer_distro_name(source_type: str, url: str) -> str:
    """根据源类型和 URL 推断适用发行版/系统"""
    lower_url = (url or "").lower()
    if source_type == PatchSourceType.WSUS:
        return "Windows Server"
    if source_type == PatchSourceType.YUM_REPO:
        if "rocky" in lower_url:
            return "Rocky Linux"
        if "centos" in lower_url:
            return "CentOS"
        if "rhel" in lower_url or "redhat" in lower_url:
            return "RHEL"
        return ""
    if source_type == PatchSourceType.DNF_REPO:
        if "rocky" in lower_url:
            return "Rocky Linux"
        if "centos" in lower_url or "centos-stream" in lower_url:
            return "CentOS Stream"
        if "rhel" in lower_url or "redhat" in lower_url:
            return "RHEL"
        return ""
    if source_type == PatchSourceType.APT_REPO:
        if "ubuntu" in lower_url:
            return "Ubuntu"
        if "debian" in lower_url:
            return "Debian"
        return ""
    return ""


class PatchSourceSerializer(TeamSerializer):
    """补丁源序列化器"""

    source_type_display = serializers.CharField(source="get_source_type_display", read_only=True)
    connectivity_status_display = serializers.CharField(
        source="get_connectivity_status_display", read_only=True
    )
    auth_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_auth_password = serializers.SerializerMethodField()

    class Meta:
        model = PatchSource
        fields = [
            "id",
            "name",
            "source_type",
            "source_type_display",
            "url",
            "distro_name",
            "os_version",
            "arch",
            "proxy_host",
            "proxy_port",
            "auth_user",
            "auth_password",
            "has_auth_password",
            "is_enabled",
            "connectivity_status",
            "connectivity_status_display",
            "last_checked_at",
            "team",
            "team_name",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "connectivity_status",
            "last_checked_at",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        ]

    @staticmethod
    def get_has_auth_password(obj: PatchSource) -> bool:
        """只返回凭据是否存在，绝不把解密后的密码发送到前端。"""
        return bool(obj.auth_password)

    def validate_source_type(self, value: str) -> str:
        if value not in MVP_SOURCE_TYPES:
            raise serializers.ValidationError("MVP 阶段仅支持 WSUS、yum repo、dnf repo、apt repo 四种类型")
        return value

    def validate_name(self, value):
        """同 team 下名称唯一。"""
        if not value:
            return value
        request = self.context.get("request")
        team_id = None
        if request:
            from apps.core.utils.team_utils import get_current_team
            team_id = get_current_team(request)
        qs = PatchSource.objects.filter(name=value)
        if team_id:
            qs = qs.filter(team__contains=[int(team_id)])
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("同名补丁源已存在")
        return value

    def validate(self, attrs):
        source_type = attrs.get("source_type")
        url = attrs.get("url", "")
        if source_type and source_type in MVP_SOURCE_TYPES and not attrs.get("distro_name"):
            attrs["distro_name"] = infer_distro_name(source_type, url)
        return attrs

    @staticmethod
    def _encrypt_password(validated_data):
        if "auth_password" in validated_data and validated_data["auth_password"]:
            EncryptMixin.encrypt_field("auth_password", validated_data)
        return validated_data

    def create(self, validated_data):
        return super().create(self._encrypt_password(validated_data))

    def update(self, instance, validated_data):
        # 编辑表单未输入新密码时复用已保存凭据，不能把空字符串覆盖进库。
        if "auth_password" in validated_data and not validated_data["auth_password"]:
            validated_data.pop("auth_password")
        return super().update(instance, self._encrypt_password(validated_data))
