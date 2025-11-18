from rest_framework import serializers

from apps.system_mgmt.models import ErrorLog


class ErrorLogSerializer(serializers.ModelSerializer):
    """错误日志序列化器"""

    class Meta:
        model = ErrorLog
        fields = [
            "id",
            "username",
            "app",
            "module",
            "error_message",
            "domain",
            "created_at",
        ]
        read_only_fields = fields
