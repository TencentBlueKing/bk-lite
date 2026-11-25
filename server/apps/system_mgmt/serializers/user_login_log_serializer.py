from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import UserLoginLog
from apps.system_mgmt.utils.login_log_utils import format_client_display, format_login_method_display


class UserLoginLogSerializer(serializers.ModelSerializer):
    """用户登录日志序列化器"""

    status_display = serializers.SerializerMethodField()
    login_method_display = serializers.SerializerMethodField()
    client_display = serializers.SerializerMethodField()
    login_time = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = UserLoginLog
        fields = "__all__"

    def __init__(self, instance=None, data=empty, **kwargs):
        super(UserLoginLogSerializer, self).__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") if self.context.get("request") else "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)

    def get_status_display(self, obj):
        """获取状态的翻译显示"""
        if obj.status == UserLoginLog.STATUS_SUCCESS:
            return self.loader.get("status.success") or "Success"
        elif obj.status == UserLoginLog.STATUS_FAILED:
            return self.loader.get("status.failed") or "Failed"
        return obj.get_status_display()

    def get_login_method_display(self, obj):
        return format_login_method_display(obj.login_method, obj.used_otp, loader=self.loader)

    def get_client_display(self, obj):
        return format_client_display(obj.os_info, obj.browser_info, loader=self.loader)
