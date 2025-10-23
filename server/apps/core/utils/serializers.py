from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.permission_utils import get_permission_rules
from apps.system_mgmt.models import User


class UsernameSerializer(serializers.ModelSerializer):
    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        user_list = User.objects.all().values("username", "display_name", "domain")
        self.user_map = {}
        for i in user_list:
            self.user_map[f"{i['username']}@{i['domain']}"] = i["display_name"]

    def to_representation(self, instance):
        response = super().to_representation(instance)
        if "created_by" in list(response.keys()):
            username = f"{response['created_by']}@{response.get('domain', 'domain.com')}"
            response["created_by"] = self.user_map.get(username, response["created_by"])
        if "updated_by" in list(response.keys()):
            username = f"{response['updated_by']}@{response.get('updated_by_domain', 'domain.com')}"
            response["updated_by"] = self.user_map.get(username, response["updated_by"])
        return response


class I18nSerializer(UsernameSerializer):
    def to_representation(self, instance):
        response = super().to_representation(instance)
        if "is_build_in" in list(response.keys()):
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


class AuthSerializer(UsernameSerializer):
    permissions = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context["request"]
        self.rule_map = {}
        current_team = request.COOKIES.get("current_team", "0")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        app_name = self.get_app_name()
        permission_rules = get_permission_rules(request.user, current_team, app_name, self.permission_key, include_children)
        self.auth_team = permission_rules.get("team", [])
        self.rule_map = {}
        for i in permission_rules.get("instance", []):
            if int(i["id"]) in self.rule_map:
                permission = list(set(self.rule_map[int(i["id"])] + i["permission"]))
                self.rule_map[int(i["id"])] = permission
            else:
                self.rule_map[int(i["id"])] = i["permission"]

    def get_app_name(self):
        """获取当前序列化器所属的应用名称"""
        module_path = self.__class__.__module__
        if "apps." in module_path:
            # 从模块路径中提取应用名称，如 apps.opspilot.serializers -> opspilot
            parts = module_path.split(".")
            if len(parts) >= 2 and parts[0] == "apps":
                return parts[1]
        return None

    def get_permissions(self, instance):
        if hasattr(instance, "team"):
            if self.auth_team and instance.team and set(self.auth_team).intersection(set(instance.team)):
                return ["View", "Operate"]
        return self.rule_map.get(instance.id, ["View", "Operate"])
