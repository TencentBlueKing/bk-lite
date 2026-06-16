from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


def _build_actor_context(request):
    current_team = request.COOKIES.get("current_team")
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        # 与 monitor_instance/node_mgmt 两处保持一致：用户面 scoped 查询（get_group_users_scoped /
        # search_channel_list_scoped）依赖 group_list 做组织范围判断，此前缺失会导致 scope 判错（#3334）
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


class SystemMgmtView(ViewSet):
    @action(methods=["get"], detail=False, url_path="user_all")
    def get_user_all(self, request):
        # 通知人列表必须收口到调用方授权范围，避免把全平台用户暴露给任意登录用户（#3140）
        actor_context = _build_actor_context(request)
        data = SystemMgmtUtils.get_user_all(actor_context=actor_context)
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="search_channel_list")
    def search_channel_list(self, request):
        actor_context = _build_actor_context(request)
        include_children = request.COOKIES.get("include_children", "0") == "1"
        data = SystemMgmtUtils.search_channel_list(
            actor_context,
            teams=[actor_context["current_team"]],
            include_children=include_children,
        )
        return WebUtils.response_success(data)
