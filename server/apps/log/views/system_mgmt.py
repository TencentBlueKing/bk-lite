from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import ViewSet

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.log.utils.system_mgmt import SystemMgmtUtils
from apps.rpc.system_mgmt import SystemMgmt


def _build_actor_context(request, *, require_current_team=False):
    current_team = get_current_team(request)
    if current_team not in (None, ""):
        try:
            current_team = int(current_team)
        except (TypeError, ValueError) as exc:
            if require_current_team:
                raise ValidationAppException("current_team 参数非法") from exc
            current_team = None
    else:
        if require_current_team:
            return None
        current_team = None

    user = getattr(request, "user", None)
    return {
        "username": getattr(user, "username", None),
        "domain": getattr(user, "domain", "domain.com"),
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        "group_list": normalize_user_group_ids(getattr(user, "group_list", [])),
    }


class SystemMgmtView(ViewSet):
    @action(methods=["get"], detail=False, url_path="user_all")
    def get_user_all(self, request):
        organization_ids = request.GET.get("organization_ids")
        if organization_ids not in (None, ""):
            # 策略编辑：按策略所属组织（∩ 可分配组织）渲染通知人
            data = SystemMgmtUtils.get_users_by_organizations(
                actor_context=_build_actor_context(request),
                organization_ids=organization_ids,
            )
            return WebUtils.response_success(data)

        current_team = get_current_team(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        result = SystemMgmt().get_group_users(group=current_team, include_children=include_children)
        return WebUtils.response_success(result["data"])

    @action(methods=["get"], detail=False, url_path="search_channel_list")
    def search_channel_list(self, request):
        channel_type = request.GET.get("channel_type", "")
        actor_context = _build_actor_context(request, require_current_team=True)
        if actor_context is None:
            return WebUtils.response_success([])

        result = SystemMgmt().search_channel_list_scoped(
            actor_context,
            channel_type=channel_type,
            teams=None,
            include_children=actor_context["include_children"],
        )
        if not isinstance(result, dict):
            raise BaseAppException("通知通道查询失败")
        if result.get("result") is False:
            raise PermissionDenied(result.get("message") or "通知通道查询失败")
        return WebUtils.response_success(result.get("data") or [])
