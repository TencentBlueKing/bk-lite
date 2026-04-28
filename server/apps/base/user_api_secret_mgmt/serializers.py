from rest_framework import serializers
from rest_framework.fields import empty

from apps.base.models.user import UserAPISecret


class BaseUserAPISecretSerializer(serializers.ModelSerializer):
    team_name = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        groups = request.user.group_list
        self.group_map = {i["id"]: i["name"] for i in groups if isinstance(i, dict) and "id" in i and "name" in i}

    def get_team_name(self, instance):
        return self.group_map.get(instance.team, instance.team) if instance.team else ""


class UserAPISecretSerializer(BaseUserAPISecretSerializer):
    api_secret_preview = serializers.SerializerMethodField()

    class Meta:
        model = UserAPISecret
        fields = ("id", "username", "domain", "team", "team_name", "created_at", "updated_at", "api_secret_preview")

    def get_api_secret_preview(self, instance):
        return f"{instance.api_secret[:4]}********" if instance.api_secret else ""


class UserAPISecretCreateSerializer(BaseUserAPISecretSerializer):
    class Meta:
        model = UserAPISecret
        fields = "__all__"
