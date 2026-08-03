"""补丁管理实例权限序列化基类。"""

from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils import viewset_utils
from apps.core.utils.serializers import TeamSerializer
from apps.core.utils.team_utils import get_current_team


class PatchPermissionSerializer(TeamSerializer):
    """为列表实例返回 ``permission``，供 PermissionWrapper 使用。"""

    permission = serializers.SerializerMethodField()
    permission_key = ""

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        request = self.context.get("request")
        self._permission_teams: set[int] = set()
        self._instance_permissions: dict[int, set[str]] = {}
        self._is_superuser = bool(
            request and getattr(request.user, "is_superuser", False)
        )
        if not request or self._is_superuser or not self.permission_key:
            return

        current_team = get_current_team(request, "0")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        rules = viewset_utils.get_permission_rules(
            request.user,
            current_team,
            "patch_mgmt",
            self.permission_key,
            include_children,
        )
        self._permission_teams = {
            int(team_id)
            for team_id in rules.get("team", [])
            if str(team_id).isdigit()
        }
        for item in rules.get("instance", []):
            try:
                instance_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            self._instance_permissions.setdefault(instance_id, set()).update(
                item.get("permission") or []
            )

    def get_permission(self, instance):
        if self._is_superuser:
            return ["View", "Operate"]
        instance_teams = {
            int(team_id)
            for team_id in (getattr(instance, "team", []) or [])
            if str(team_id).isdigit()
        }
        if self._permission_teams.intersection(instance_teams):
            return ["View", "Operate"]
        permissions = self._instance_permissions.get(instance.id, set())
        return [name for name in ("View", "Operate") if name in permissions]
