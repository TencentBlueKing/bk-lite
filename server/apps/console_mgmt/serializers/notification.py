from rest_framework import serializers

from apps.console_mgmt.models import Notification

MARK_BATCH_READ_MAX_IDS = 1000


class NotificationSerializer(serializers.ModelSerializer):
    """通知消息序列化器"""

    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ["id", "notification_time", "app_module", "content", "is_read", "source"]
        read_only_fields = ["id", "notification_time"]

    def get_is_read(self, obj):
        """从 annotate 的 user_is_read 取值，未标注时默认未读"""
        if hasattr(obj, "user_is_read"):
            return obj.user_is_read
        return False


class MarkBatchAsReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=MARK_BATCH_READ_MAX_IDS,
    )
