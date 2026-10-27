# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.models import IncidentUpdate
from apps.alerts.utils.i18n import resolve_alerts_language


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
        # parent 只在创建回复时由视图写入。编辑已有记录时保持原值，避免改挂到其他事故。
        read_only_fields = ["id", "incident", "parent", "author", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance is not None and _parent_assignment_rejected(
            self.instance, getattr(self, "initial_data", None)
        ):
            raise serializers.ValidationError({"parent": _parent_locked_message(self)})
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop("parent", None)
        return super().update(instance, validated_data)

    def get_author_display_name(self, obj):
        author_user_map = self.context.get("author_user_map")
        if author_user_map:
            return author_user_map.get(obj.author, obj.author)
        return obj.author

    def _replies_for_serialization(self, obj):
        prefetched = getattr(obj, "_prefetched_objects_cache", None)
        if prefetched is not None and "replies" in prefetched:
            return list(prefetched["replies"])

        cache = self.context.setdefault("_incident_update_replies", {})
        key = obj.pk
        if key not in cache:
            cache[key] = list(obj.replies.order_by("created_at"))
        return cache[key]

    def get_replies(self, obj):
        replies = self._replies_for_serialization(obj)
        if not replies:
            return []
        return IncidentUpdateReplySerializer(replies, many=True, context=self.context).data

    def get_reply_count(self, obj):
        return len(self._replies_for_serialization(obj))


def _parent_assignment_rejected(instance, payload):
    """请求带了不同 parent 时拒绝。不查库，也不回写已有记录。"""
    if payload is None:
        return False
    try:
        supplied = "parent" in payload
    except TypeError:
        return False
    if not supplied:
        return False

    raw = payload.get("parent")
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return True

    incoming = _coerce_parent_id(raw)
    if incoming is None or incoming == instance.id:
        return True
    return incoming != instance.parent_id


def _coerce_parent_id(raw):
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _parent_locked_message(serializer):
    request = getattr(serializer, "context", {}).get("request")
    user = getattr(request, "user", None)
    language = resolve_alerts_language(getattr(user, "locale", None))
    if language == "en":
        return "The parent of an existing update cannot be changed."
    return "不能修改已有协作更新的父级。"
