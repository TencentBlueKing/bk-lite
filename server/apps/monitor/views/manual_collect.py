from rest_framework import viewsets
from rest_framework.decorators import action
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.manual_collect import ManualCollectService
from apps.rpc.node_mgmt import NodeMgmt


class ManualCollect(viewsets.ViewSet):

    @action(methods=['get'], detail=False, url_path='cloud_region_list')
    def cloud_area_list(self, request):
        data = NodeMgmt().cloud_region_list()
        return WebUtils.response_success(data)

    # 创建手动监控实例
    @action(methods=['post'], detail=False, url_path='create_manual_instance')
    def create_manual_instance(self, request):
        data = ManualCollectService.create_manual_collect_instance(request.data)
        return WebUtils.response_success(data)

    # 生成安装命令
    @action(methods=['post'], detail=False, url_path='generate_install_command')
    def generate_install_command(self, request):
        data = ManualCollectService.generate_install_command(request.data["instance_id"], request.data["cloud_region_id"])
        return WebUtils.response_success(data)

    # 检查手动采集状态
    @action(methods=['post'], detail=False, url_path='check_collect_status')
    def check_collect_status(self, request):
        data = ManualCollectService.check_collect_status(request.data["monitor_object_id"], request.data["instance_id"])
        return WebUtils.response_success(data)
