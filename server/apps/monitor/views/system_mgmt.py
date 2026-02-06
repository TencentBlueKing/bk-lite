from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


class SystemMgmtView(ViewSet):
    @action(methods=["get"], detail=False, url_path="user_all")
    def get_user_all(self, request):
        current_team = request.COOKIES.get("current_team")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        data = SystemMgmtUtils.get_user_all(
            group=int(current_team), include_children=include_children
        )
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="search_channel_list")
    def search_channel_list(self, request):
        current_team = request.COOKIES.get("current_team")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        data = SystemMgmtUtils.search_channel_list(
            teams=[int(current_team)], include_children=include_children
        )
        return WebUtils.response_success(data)
