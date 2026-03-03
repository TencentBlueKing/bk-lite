from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtView(ViewSet):
    @action(methods=["get"], detail=False, url_path="user_all")
    def get_user_all(self, request):
        current_team = request.COOKIES.get("current_team")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        result = SystemMgmt().get_group_users(
            group=current_team, include_children=include_children
        )
        return WebUtils.response_success(result["data"])

    @action(methods=["get"], detail=False, url_path="search_channel_list")
    def search_channel_list(self, request):
        channel_type = request.GET.get("channel_type", "")
        current_team = request.COOKIES.get("current_team")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        teams = [current_team] if current_team else None
        result = SystemMgmt().search_channel_list(
            channel_type=channel_type, teams=teams, include_children=include_children
        )
        return WebUtils.response_success(result["data"])
