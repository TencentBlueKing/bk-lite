from rest_framework import serializers

from apps.opspilot.models import ChatApplication


class ChatApplicationSerializer(serializers.ModelSerializer):
    """聊天应用序列化器"""

    app_type_display = serializers.CharField(source="get_app_type_display", read_only=True)
    bot_name = serializers.CharField(source="bot.name", read_only=True)

    class Meta:
        model = ChatApplication
        fields = [
            "id",
            "bot",
            "bot_name",
            "node_id",
            "app_type",
            "app_type_display",
            "app_name",
            "app_description",
            "app_tags",
            "app_icon",
            "node_config",
        ]
        read_only_fields = [
            "id",
            "bot",
            "bot_name",
            "node_id",
            "app_type",
            "app_type_display",
            "app_name",
            "app_description",
            "app_tags",
            "app_icon",
            "node_config",
        ]
