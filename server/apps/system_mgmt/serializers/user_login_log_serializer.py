from rest_framework import serializers

from apps.system_mgmt.models import UserLoginLog


class UserLoginLogSerializer(serializers.ModelSerializer):
    """用户登录日志序列化器"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
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


class UserLoginLogListSerializer(serializers.ModelSerializer):
    """用户登录日志列表序列化器（简化版）"""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
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
