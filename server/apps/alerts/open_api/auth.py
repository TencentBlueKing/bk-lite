from dataclasses import dataclass

from .errors import AlertsOpenAPIError


@dataclass(frozen=True)
class AlertsOpenAPIContext:
    user: object
    team_id: int

    @property
    def username(self) -> str:
        return getattr(self.user, "username", "") or ""

    @classmethod
    def from_request(cls, request):
        if not getattr(request, "api_pass", False):
            raise AlertsOpenAPIError("alerts.auth.api_secret_required", "必须使用 API Secret", 403)
        groups = getattr(request.user, "group_list", []) or []
        if len(groups) != 1:
            raise AlertsOpenAPIError("alerts.auth.invalid_team", "API Secret 团队绑定无效", 403)
        raw_team = groups[0].get("id") if isinstance(groups[0], dict) else groups[0]
        try:
            team_id = int(raw_team)
        except (TypeError, ValueError):
            raise AlertsOpenAPIError("alerts.auth.invalid_team", "API Secret 团队绑定无效", 403) from None
        return cls(user=request.user, team_id=team_id)

    def require_feature(self, permission: str):
        if getattr(self.user, "is_superuser", False):
            return
        user_permissions = getattr(self.user, "permission", {}) or {}
        alarm_perms = set(user_permissions.get("alarm", set()) or [])
        if permission not in alarm_perms:
            raise AlertsOpenAPIError("alerts.permission.denied", "权限不足", 403)
