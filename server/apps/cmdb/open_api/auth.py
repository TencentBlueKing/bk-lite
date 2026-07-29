from dataclasses import dataclass

from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.core.utils.permission_utils import get_permission_rules

from .errors import CMDBOpenAPIError


@dataclass(frozen=True)
class CMDBOpenAPIContext:
    user: object
    team_id: int

    @property
    def user_groups(self):
        return [{"id": self.team_id}]

    @classmethod
    def from_request(cls, request):
        if not getattr(request, "api_pass", False):
            raise CMDBOpenAPIError("cmdb.auth.api_secret_required", "必须使用 API Secret", 403)
        groups = getattr(request.user, "group_list", []) or []
        if len(groups) != 1:
            raise CMDBOpenAPIError("cmdb.auth.invalid_team", "API Secret 团队绑定无效", 403)
        raw_team = groups[0].get("id") if isinstance(groups[0], dict) else groups[0]
        try:
            team_id = int(raw_team)
        except (TypeError, ValueError):
            raise CMDBOpenAPIError("cmdb.auth.invalid_team", "API Secret 团队绑定无效", 403) from None
        return cls(user=request.user, team_id=team_id)

    def require_feature(self, permission: str):
        if getattr(self.user, "is_superuser", False):
            return
        user_permissions = getattr(self.user, "permission", {}) or {}
        if permission not in set(user_permissions.get("cmdb", set())):
            raise CMDBOpenAPIError("cmdb.permission.denied", "权限不足", 403)

    def permission_map(self, model_id: str, permission_type: str):
        if getattr(self.user, "is_superuser", False):
            return {self.team_id: {"permission_instances_map": {}, "inst_names": []}}
        key = f"{permission_type}.{model_id}" if model_id else permission_type
        rules = get_permission_rules(
            user=self.user,
            current_team=self.team_id,
            app_name="cmdb",
            permission_key=key,
            include_children=False,
        )
        return CmdbRulesFormatUtil.build_permission_rule_map(
            user_teams=[self.team_id],
            permission_rules=rules if isinstance(rules, dict) else {},
            fallback_team_id=self.team_id,
        )
