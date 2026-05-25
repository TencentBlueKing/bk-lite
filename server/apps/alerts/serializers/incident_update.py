# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.models import IncidentUpdate


class IncidentUpdateReplySerializer(serializers.ModelSerializer):
    """回复的序列化器（不再嵌套）"""

    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    author_display_name = serializers.SerializerMethodField()

    class Meta:
        model = IncidentUpdate
        fields = [
            "id",
            "parent",
            "author",
            "author_display_name",
            "content",
            "attachments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "parent", "author", "created_at", "updated_at"]

    def get_author_display_name(self, obj):
        author_user_map = self.context.get("author_user_map")
        if author_user_map:
            return author_user_map.get(obj.author, obj.author)
        return obj.author


class IncidentUpdateSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    author_display_name = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = IncidentUpdate
        fields = [
            "id",
            "incident",
            "parent",
            "author",
            "author_display_name",
            "update_type",
            "content",
            "attachments",
            "is_key_info",
            "created_at",
            "updated_at",
            "replies",
            "reply_count",
        ]
        read_only_fields = ["id", "incident", "author", "created_at", "updated_at"]

    def get_author_display_name(self, obj):
        author_user_map = self.context.get("author_user_map")
        if author_user_map:
            return author_user_map.get(obj.author, obj.author)
        return obj.author

    def get_replies(self, obj):
        replies_qs = obj.replies.all().order_by("created_at")
        if not replies_qs.exists():
            return []
        return IncidentUpdateReplySerializer(
            replies_qs, many=True, context=self.context
        ).data

    def get_reply_count(self, obj):
        return obj.replies.count()
