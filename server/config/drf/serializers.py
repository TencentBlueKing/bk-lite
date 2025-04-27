from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.fields import empty


class I18nSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        response = super().to_representation(instance)
        for key in response.keys():
            if isinstance(response[key], str):
                response[key] = _(response[key])
        return response


class TeamSerializer(I18nSerializer):
    team_name = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        groups = request.user.group_list
        self.group_map = {i["id"]: i["name"] for i in groups}

    def get_team_name(self, instance):
        return [self.group_map.get(i) for i in instance.team if i in self.group_map]


class AuthSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        self.rule_map = {}
        if hasattr(self, "permission_key"):
            if "." in self.permission_key:
                keys = self.permission_key.split(".")
                rules = request.user.rules.get(keys[0], {}).get(keys[1], [])
            else:
                rules = request.user.rules.get(self.permission_key, [])
            self.rule_map = {int(i["id"]): i["permission"] for i in rules}

    def get_permissions(self, instance):
        return self.rule_map.get(instance.id, ["View", "Operate"])
