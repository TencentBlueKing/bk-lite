from rest_framework import serializers

from apps.itsm.models import DataDictionary, DataDictionaryItem, HandlerGroup, NotifyTemplate, StatusTransition, TicketStatus
from apps.system_mgmt.models import User


class TicketStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketStatus
        fields = ["id", "key", "name", "color", "description", "kind"]
        read_only_fields = ["id", "kind"]


class StatusTransitionSerializer(serializers.ModelSerializer):
    from_id = serializers.IntegerField(source="from_status_id")
    to_id = serializers.IntegerField(source="to_status_id")
    from_name = serializers.CharField(source="from_status.name", read_only=True)
    to_name = serializers.CharField(source="to_status.name", read_only=True)

    class Meta:
        model = StatusTransition
        fields = ["id", "from_id", "to_id", "from_name", "to_name", "name"]
        read_only_fields = ["id", "from_name", "to_name"]


class HandlerGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = HandlerGroup
        fields = ["id", "name", "members", "leaders"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        if not str(value or "").strip():
            raise serializers.ValidationError("请填写处理组名称")
        return value.strip()


class NotifyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotifyTemplate
        fields = ["id", "event", "title_tpl", "content_tpl", "is_builtin"]
        read_only_fields = ["id", "is_builtin"]


class DictionarySerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDictionary
        fields = ["id", "key", "name"]
        read_only_fields = ["id"]


class DictionaryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDictionaryItem
        fields = ["id", "key", "label", "order"]
        read_only_fields = ["id"]


class UserSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "display_name"]
