from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.log.utils.system_mgmt import SystemMgmtUtils
from apps.rpc.system_mgmt import SystemMgmt
from apps.core.utils.team_utils import get_current_team


def _build_actor_context(request):
    current_team = get_current_team(request)
    if current_team not in (None, ""):
        try:
            current_team = int(current_team)
        except (TypeError, ValueError):
            current_team = None
    else:
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
        current_team = get_current_team(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        teams = [int(current_team)] if current_team else None
        result = SystemMgmt().search_channel_list(channel_type=channel_type, teams=teams, include_children=include_children)
        return WebUtils.response_success(result["data"])
