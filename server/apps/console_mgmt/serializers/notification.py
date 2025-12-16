from rest_framework import serializers

from apps.console_mgmt.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """通知消息序列化器"""

    class Meta:
        model = Notification
        fields = ["id", "notification_time", "app_module", "content", "is_read"]
        read_only_fields = ["id", "notification_time"]
