from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import install_controller, install_collector, uninstall_controller


class InstallerViewSet(ViewSet):

    @action(detail=False, methods=["post"], url_path="controller/install")
    def controller_install(self, request):
        task_id = InstallerService.install_controller(
            request.data["cloud_region_id"],
            request.data["work_node"],
            request.data["package_id"],
            request.data["nodes"],
        )
        install_controller.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="controller/uninstall")
    def controller_uninstall(self, request):
        task_id = InstallerService.uninstall_controller(
            request.data["cloud_region_id"],
            request.data["work_node"],
            request.data["nodes"],
        )
        uninstall_controller.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    # @action(detail=False, methods=["post"], url_path="controller/restart")
    # def controller_restart(self, request):
    #     restart_controller.delay(request.data)
    #     return WebUtils.response_success()

    @action(detail=False, methods=["post"], url_path="controller/task/(?P<task_id>[^/.]+)/nodes")
    def controller_install_nodes(self, request, task_id):
        data = InstallerService.install_controller_nodes(task_id)
        return WebUtils.response_success(data)

    # 采集器
    @action(detail=False, methods=["post"], url_path="collector/install")
    def collector_install(self, request):
        task_id = InstallerService.install_collector(request.data["collector_package"], request.data["nodes"])
        install_collector.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="collector/install/(?P<task_id>[^/.]+)/nodes")
    def collector_install_nodes(self, request, task_id):
        data = InstallerService.install_collector_nodes(task_id)
        return WebUtils.response_success(data)

    # 获取安装命令
    @action(detail=False, methods=["post"], url_path="get_install_command")
    def get_install_command(self, request):
        data = InstallerService.get_install_command(
            request.user.username,
            request.data["ip"],
            request.data["os"],
            request.data["package_name"],
            request.data["cloud_region_id"],
            request.data.get("organizations", []),
            request.data.get("node_name", ""),
        )
        return WebUtils.response_success(data)
