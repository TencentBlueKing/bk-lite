from rest_framework import serializers

from apps.alerts.models import IncidentIMMember
from apps.system_mgmt.models import User


class IncidentIMGroupCreateSerializer(serializers.Serializer):
    channel_id = serializers.IntegerField(min_value=1)
    group_name = serializers.CharField(min_length=1, max_length=255, trim_whitespace=True)
    owner_username = serializers.CharField(max_length=User._meta.get_field("username").max_length)
    continuous_sync_enabled = serializers.BooleanField(default=True)


class IncidentIMGroupSettingsSerializer(serializers.Serializer):
    continuous_sync_enabled = serializers.BooleanField()


class IncidentIMGroupUnlinkSerializer(serializers.Serializer):
    group_name = serializers.CharField(max_length=255, trim_whitespace=False)


class IncidentIMMemberSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    error_code = serializers.CharField(source="last_error_code")
    error_message = serializers.SerializerMethodField()

    class Meta:
        model = IncidentIMMember
        fields = (
            "username",
            "display_name",
            "role",
            "mapping_status",
            "sync_status",
            "error_code",
            "error_message",
            "updated_at",
        )

    def get_display_name(self, obj):
        display_names = self.context.get("display_names", {})
        return display_names.get(obj.username, obj.username)

    def get_error_message(self, obj):
        return safe_member_error_message(obj.last_error_code)


def serialize_resolved_member(member):
    return {
        "username": member.username,
        "display_name": member.display_name,
        "role": member.role,
        "mapping_status": member.mapping_status,
        "error_code": member.error_code,
        "error_message": safe_member_error_message(member.error_code),
    }


def member_display_names(members):
    usernames = [member.username for member in members]
    return dict(User.objects.filter(username__in=usernames).values_list("username", "display_name"))


_SAFE_MEMBER_ERROR_MESSAGES = {
    "IM_USER_MAPPING_CONFLICT": "用户映射存在冲突",
    "IM_USER_MAPPING_NOT_FOUND": "未找到飞书账号映射",
    "IM_USER_RECEIVE_ID_MISSING": "飞书账号缺少可用的接收标识",
    "IM_MEMBER_INVALID": "飞书账号不可用，请检查用户状态或应用可见范围",
    "IM_MEMBER_ADD_FAILED": "加入失败，请重试或联系管理员",
    "provider.auth_failed": "飞书渠道凭据异常，请联系管理员",
    "provider.permission_denied": "飞书渠道权限不足，请联系管理员",
    "provider.invalid_config": "飞书渠道配置异常，请联系管理员",
    "provider.group_not_found": "飞书群不存在或机器人已离开群聊",
    "provider.timeout": "飞书服务暂时不可用，请稍后重试",
    "provider.rate_limited": "飞书请求频率受限，请稍后重试",
    "provider.request_failed": "飞书服务暂时不可用，请稍后重试",
}


def safe_member_error_message(error_code):
    code = str(error_code or "").strip()
    if not code:
        return ""
    return _SAFE_MEMBER_ERROR_MESSAGES.get(code, "加入失败，请重试或联系管理员")
