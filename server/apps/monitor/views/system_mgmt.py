from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils


class SystemMgmtView(ViewSet):
    @action(methods=['get'], detail=False, url_path='user_all')
    def get_user_all(self, request):
        # todo 需要组织和是否包含子组织参数
        data = SystemMgmtUtils.get_user_all()
        return WebUtils.response_success(data)

    @action(methods=['get'], detail=False, url_path='search_channel_list')
    def search_channel_list(self, request):
        # todo 需要组织和是否包含子组织参数
        data = SystemMgmtUtils.search_channel_list()
        return WebUtils.response_success(data)
