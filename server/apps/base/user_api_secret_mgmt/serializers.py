from rest_framework import serializers
from rest_framework.fields import empty

from apps.base.models import UserAPISecret


class UserAPISecretSerializer(serializers.ModelSerializer):
    team_name = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        groups = request.user.group_list
        self.group_map = {i["id"]: i["name"] for i in groups}

    class Meta:
        model = UserAPISecret
        fields = "__all__"

    def get_team_name(self, instance):
        return self.group_map.get(instance.team, instance.team) if instance.team else ""
