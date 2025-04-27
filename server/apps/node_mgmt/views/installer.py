from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import install_controller, install_collector, uninstall_controller


class InstallerViewSet(ViewSet):

    @swagger_auto_schema(
        operation_id="controller_install",
        operation_summary="安装控制器",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'cloud_region_id': openapi.Schema(type=openapi.TYPE_INTEGER,description="云区域ID"),
                'work_node': openapi.Schema(type=openapi.TYPE_INTEGER,description="工作节点ID"),
                'package_id': openapi.Schema(type=openapi.TYPE_NUMBER,description="控制器包版本ID"),
                'nodes': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'os': openapi.Schema(type=openapi.TYPE_STRING,description="操作系统"),
                        'ip': openapi.Schema(type=openapi.TYPE_STRING,description="节点IP"),
                        'port': openapi.Schema(type=openapi.TYPE_INTEGER,description="节点端口"),
                        'username': openapi.Schema(type=openapi.TYPE_STRING,description="用户名"),
                        'password': openapi.Schema(type=openapi.TYPE_STRING,description="密码"),
                        'organizations': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(type=openapi.TYPE_STRING,description="所属组织"),
                        ),
                    }
                ),
            }
        ),
        tags=['Installer']
    )
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

    @swagger_auto_schema(
        operation_id="controller_uninstall",
        operation_summary="卸载控制器",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'cloud_region_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="云区域ID"),
                'work_node': openapi.Schema(type=openapi.TYPE_INTEGER, description="工作节点ID"),
                'nodes': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'os': openapi.Schema(type=openapi.TYPE_STRING, description="操作系统"),
                        'ip': openapi.Schema(type=openapi.TYPE_STRING, description="节点IP"),
                        'port': openapi.Schema(type=openapi.TYPE_INTEGER, description="节点端口"),
                        'username': openapi.Schema(type=openapi.TYPE_STRING, description="用户名"),
                        'password': openapi.Schema(type=openapi.TYPE_STRING, description="密码"),
                    }
                ),
            }
        ),
        tags=['Installer']
    )
    @action(detail=False, methods=["post"], url_path="controller/uninstall")
    def controller_uninstall(self, request):
        task_id = InstallerService.uninstall_controller(
            request.data["cloud_region_id"],
            request.data["work_node"],
            request.data["nodes"],
        )
        uninstall_controller.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    # @swagger_auto_schema(
    #     operation_id="controller_restart",
    #     operation_summary="重启控制器",
    #     tags=['Installer']
    # )
    # @action(detail=False, methods=["post"], url_path="controller/restart")
    # def controller_restart(self, request):
    #     restart_controller.delay(request.data)
    #     return WebUtils.response_success()

    @swagger_auto_schema(
        operation_id="controller_task_nodes",
        operation_summary="控制器任务节点信息",
        manual_parameters=[
            openapi.Parameter('task_id', openapi.IN_PATH, description="任务ID", type=openapi.TYPE_STRING),
        ],
        tags=['Installer']
    )
    @action(detail=False, methods=["post"], url_path="controller/task/(?P<task_id>[^/.]+)/nodes")
    def controller_install_nodes(self, request, task_id):
        data = InstallerService.install_controller_nodes(task_id)
        return WebUtils.response_success(data)

    # 采集器
    @swagger_auto_schema(
        operation_id="collector_install",
        operation_summary="安装采集器",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'collector_package': openapi.Schema(type=openapi.TYPE_NUMBER, description="采集器版本ID"),
                'nodes': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="节点ID",
                    ),
                ),
            }
        ),
        tags=['Installer']
    )
    @action(detail=False, methods=["post"], url_path="collector/install")
    def collector_install(self, request):
        task_id = InstallerService.install_collector(request.data["collector_package"], request.data["nodes"])
        install_collector.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @swagger_auto_schema(
        operation_id="collector_install_nodes",
        operation_summary="获取采集器安装节点信息",
        manual_parameters=[
            openapi.Parameter('task_id', openapi.IN_PATH, description="任务ID", type=openapi.TYPE_STRING)
        ],
        tags=['Installer']
    )
    @action(detail=False, methods=["post"], url_path="collector/install/(?P<task_id>[^/.]+)/nodes")
    def collector_install_nodes(self, request, task_id):
        data = InstallerService.install_collector_nodes(task_id)
        return WebUtils.response_success(data)

    # 获取安装命令
    @swagger_auto_schema(
        operation_id="get_install_command",
        operation_summary="获取安装命令",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'os': openapi.Schema(type=openapi.TYPE_STRING, description="操作系统"),
                'package_name': openapi.Schema(type=openapi.TYPE_STRING, description="包名称"),
                'cloud_region_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="云区域ID"),
            }
        ),
        tags=['Installer']
    )
    @action(detail=False, methods=["post"], url_path="get_install_command")
    def get_install_command(self, request):
        data = InstallerService.get_install_command(request.data["os"], request.data["package_name"], request.data["cloud_region_id"])
        return WebUtils.response_success(data)
