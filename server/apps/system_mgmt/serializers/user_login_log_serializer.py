from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import UserLoginLog


class UserLoginLogSerializer(serializers.ModelSerializer):
    """用户登录日志序列化器"""

    status_display = serializers.SerializerMethodField()
    login_time = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = UserLoginLog
        fields = [
            "id",
            "username",
            "source_ip",
            "status",
            "status_display",
            "domain",
            "failure_reason",
            "user_agent",
            "login_time",
            "created_at",
        ]
        read_only_fields = fields  # 所有字段都是只读的，日志不允许修改

    def __init__(self, instance=None, data=empty, **kwargs):
        super(UserLoginLogSerializer, self).__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") if self.context.get("request") else "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)

    def get_status_display(self, obj):
        """获取状态的翻译显示"""
        if obj.status == UserLoginLog.STATUS_SUCCESS:
            return self.loader.get("base_constant.status.success") or "Success"
        elif obj.status == UserLoginLog.STATUS_FAILED:
            return self.loader.get("base_constant.status.failed") or "Failed"
        return obj.get_status_display()


class UserLoginLogListSerializer(serializers.ModelSerializer):
    """用户登录日志列表序列化器（简化版）"""

    status_display = serializers.SerializerMethodField()
    login_time = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = UserLoginLog
        fields = [
            "id",
            "username",
            "source_ip",
            "status",
            "status_display",
            "failure_reason",
            "login_time",
        ]
        read_only_fields = fields

    def __init__(self, instance=None, data=empty, **kwargs):
        super(UserLoginLogListSerializer, self).__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") if self.context.get("request") else "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)

    def get_status_display(self, obj):
        """获取状态的翻译显示"""
        if obj.status == UserLoginLog.STATUS_SUCCESS:
            return self.loader.get("base_constant.status.success") or "Success"
        elif obj.status == UserLoginLog.STATUS_FAILED:
            return self.loader.get("base_constant.status.failed") or "Failed"
        return obj.get_status_display()
