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

    @classmethod
    def from_gateway(cls, *, user_info, team_ids):
        from apps.base.models import User
        from apps.core.backends import APISecretAuthBackend
        from apps.system_mgmt.utils.group_utils import GroupUtils

        authorized = set()
        for item in team_ids or []:
            try:
                authorized.add(int(item))
            except (TypeError, ValueError):
                continue
        if not authorized:
            raise AlertsOpenAPIError("alerts.auth.invalid_team", "用户未关联活动团队", 400)
        active_ids = set(GroupUtils.active_queryset(id__in=list(authorized)).values_list("id", flat=True))
        if len(active_ids) != 1:
            raise AlertsOpenAPIError("alerts.auth.invalid_team", "用户未关联活动团队", 400)
        team_id = next(iter(active_ids))

        username = (user_info or {}).get("user") or ""
        domain = (user_info or {}).get("domain") or ""
        try:
            user = User.objects.get(username=username, domain=domain)
        except User.DoesNotExist as exc:
            raise AlertsOpenAPIError("alerts.auth.authentication_required", "需要认证", 401) from exc

        user._api_secret_team_scope = True
        user._api_secret_team = team_id
        APISecretAuthBackend()._populate_user_permissions(user, team_id)
        user.group_list = [{"id": team_id}]
        return cls(user=user, team_id=team_id)

    def require_feature(self, permission: str):
        if getattr(self.user, "is_superuser", False):
            return
        user_permissions = getattr(self.user, "permission", {}) or {}
        alarm_perms = set(user_permissions.get("alarm", set()) or [])
        if permission not in alarm_perms:
            raise AlertsOpenAPIError("alerts.permission.denied", "权限不足", 403)
