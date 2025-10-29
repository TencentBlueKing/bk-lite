from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtView(ViewSet):
    @action(methods=['get'], detail=False, url_path='user_all')
    def get_user_all(self, request):
        result = SystemMgmt().get_all_users()
        return WebUtils.response_success(result["data"])

    @action(methods=['get'], detail=False, url_path='search_channel_list')
    def search_channel_list(self, request):
        channel_type = request.GET.get("channel_type", "")
        result = SystemMgmt().search_channel_list(channel_type)
        return WebUtils.response_success(result["data"])
