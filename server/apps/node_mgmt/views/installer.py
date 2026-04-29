from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from typing import Any, cast

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.models.installer import CollectorTask, CollectorTaskNode
from apps.node_mgmt.serializers.node import TaskNodesQuerySerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import (
    install_controller,
    install_collector,
    uninstall_controller,
    retry_controller,
    timeout_controller_install_task,
    CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
)
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read


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
        timeout_controller_install_task.apply_async(
            args=[task_id],
            countdown=CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
        )
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

    @action(detail=False, methods=["post"], url_path="controller/retry")
    def controller_retry(self, request):
        retry_controller.delay(
            request.data["task_id"],
            request.data["task_node_ids"],
            password=request.data.get("password"),
            private_key=request.data.get("private_key"),
            passphrase=request.data.get("passphrase"),
        )
        return WebUtils.response_success()

    # 控制器手动安装
    @action(detail=False, methods=["post"], url_path="controller/manual_install")
    def controller_manual_install(self, request):
        result = []
        for node in request.data["nodes"]:
            result.append(
                {
                    "cloud_region_id": request.data["cloud_region_id"],
                    "os": request.data["os"],
                    "package_id": request.data["package_id"],
                    "ip": node["ip"],
                    "node_id": node["node_id"],
                    "node_name": node.get("node_name", ""),
                    "organizations": node.get("organizations", []),
                }
            )
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path="controller/manual_install_status")
    def controller_manual_install_status(self, request):
        data = InstallerService.get_manual_install_status(request.data["node_ids"])
        return WebUtils.response_success(data)

    # @action(detail=False, methods=["post"], url_path="controller/restart")
    # def controller_restart(self, request):
    #     restart_controller.delay(request.data)
    #     return WebUtils.response_success()

    @action(
        detail=False,
        methods=["post"],
        url_path="controller/task/(?P<task_id>[^/.]+)/nodes",
    )
    def controller_install_nodes(self, request, task_id):
        data = InstallerService.install_controller_nodes(task_id)
        return WebUtils.response_success(data)

    # 采集器
    @action(detail=False, methods=["post"], url_path="collector/install")
    def collector_install(self, request):
        task_id = InstallerService.install_collector(request.data["collector_package"], request.data["nodes"])
        install_collector.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(
        detail=False,
        methods=["post"],
        url_path="collector/install/(?P<task_id>[^/.]+)/nodes",
    )
    def collector_install_nodes(self, request, task_id):
        serializer = TaskNodesQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)

        queryset = CollectorTaskNode.objects.filter(task_id=task_id).select_related("node").prefetch_related("node__nodeorganization_set")
        status_list = validated_data.get("status")
        if status_list:
            queryset = queryset.filter(status__in=status_list)

        page = validated_data.get("page", 1)
        page_size = validated_data.get("page_size", 20)
        start = (page - 1) * page_size
        end = start + page_size

        total = queryset.count()
        items = queryset.order_by("id")[start:end]
        data = [
            {
                "node_id": task_node.node_id,
                "status": task_node.status,
                "result": normalize_task_result_for_read(task_node.result),
                "ip": task_node.node.ip,
                "os": task_node.node.operating_system,
                "node_name": task_node.node.name,
                "organizations": [rel.organization for rel in task_node.node.nodeorganization_set.all()],
                "install_method": task_node.node.install_method,
            }
            for task_node in items
        ]

        summary_queryset = CollectorTaskNode.objects.filter(task_id=task_id)
        summary = {
            "total": summary_queryset.count(),
            "waiting": summary_queryset.filter(status="waiting").count(),
            "running": summary_queryset.filter(status="running").count(),
            "success": summary_queryset.filter(status="success").count(),
            "error": summary_queryset.filter(status="error").count(),
            "timeout": summary_queryset.filter(result__overall_status="timeout").count(),
            "cancelled": summary_queryset.filter(result__overall_status="cancelled").count(),
        }

        task_obj = CollectorTask.objects.filter(id=task_id).first()
        task_status = task_obj.status if task_obj else "waiting"

        return WebUtils.response_success(
            {
                "task_id": task_id,
                "status": task_status,
                "summary": summary,
                "items": data,
                "count": total,
                "page": page,
                "page_size": page_size,
            }
        )

    # 获取安装命令
    @action(detail=False, methods=["post"], url_path="get_install_command")
    def get_install_command(self, request):
        data = InstallerService.get_install_command(
            request.user.username,
            request.data["ip"],
            request.data["node_id"],
            request.data["os"],
            request.data["package_id"],
            request.data["cloud_region_id"],
            request.data.get("organizations", []),
            request.data.get("node_name", ""),
            install_mode=InstallerService.MANUAL_INSTALL_MODE,
            cpu_architecture=request.data.get("cpu_architecture", ""),
        )
        return WebUtils.response_success(data)

    @action(detail=False, methods=["GET"], url_path="windows/download")
    def windows_download(self, request):
        file, _ = InstallerService.download_windows_installer(request.query_params.get("arch", ""))
        return WebUtils.response_file(file, InstallerConstants.WINDOWS_INSTALLER_FILENAME)

    @action(detail=False, methods=["GET"], url_path="linux/download")
    def linux_download(self, request):
        file, _ = InstallerService.download_linux_installer(request.query_params.get("arch", ""))
        return WebUtils.response_file(file, InstallerConstants.LINUX_INSTALLER_FILENAME)

    @action(detail=False, methods=["GET"], url_path="manifest")
    def manifest(self, request):
        return WebUtils.response_success(InstallerService.installer_manifest())

    @action(detail=False, methods=["GET"], url_path="metadata/(?P<target_os>[^/.]+)")
    def metadata(self, request, target_os):
        return WebUtils.response_success(InstallerService.installer_metadata(target_os, request.query_params.get("arch", "")))
