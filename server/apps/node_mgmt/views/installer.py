from typing import Any, cast

from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope, validate_assignable_organizations
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.models.installer import CollectorTaskNode
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.serializers.installer import (
    ControllerInstallRequestSerializer,
    ControllerManualInstallRequestSerializer,
    InstallCommandRequestSerializer,
    InstallerArtifactQuerySerializer,
)
from apps.node_mgmt.serializers.node import TaskNodesQuerySerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import (
    CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
    install_collector,
    install_controller,
    retry_controller,
    timeout_controller_install_task,
    uninstall_controller,
)
from apps.node_mgmt.utils.permission import authorize_node_ids, get_authorized_node_queryset
from apps.node_mgmt.utils.task_result_schema import normalize_task_result_for_read, project_task_status_from_summary


def _validate_install_target_organizations(request, nodes):
    organizations = []
    for node in nodes:
        node_organizations = node.get("organizations")
        if not node_organizations:
            return WebUtils.response_403("User does not have permission to assign nodes to these organizations")
        organizations.extend(node_organizations)

    try:
        validate_assignable_organizations(request, organizations)
    except BaseAppException:
        return WebUtils.response_403("User does not have permission to assign nodes to these organizations")
    return None


def _authorize_existing_install_nodes(request, node_ids):
    existing_node_ids = list(Node.objects.filter(id__in=node_ids).values_list("id", flat=True))
    if not existing_node_ids:
        return None
    _, error_response = authorize_node_ids(
        request,
        existing_node_ids,
        required_permission="Operate",
    )
    return error_response


class InstallerViewSet(ViewSet):
    @action(detail=False, methods=["post"], url_path="controller/install")
    @HasPermission("cloud_region_node-Edit")
    def controller_install(self, request):
        serializer = ControllerInstallRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        organization_error = _validate_install_target_organizations(request, data["nodes"])
        if organization_error:
            return organization_error
        node_ids = [node["node_id"] for node in data["nodes"] if node.get("node_id")]
        if node_ids:
            error_response = _authorize_existing_install_nodes(request, node_ids)
            if error_response:
                return error_response
        task_id = InstallerService.install_controller(
            data["cloud_region_id"],
            data["work_node"],
            data["package_id"],
            data["nodes"],
            data["cpu_architecture"],
            request.user.username,
            getattr(request.user, "domain", "domain.com"),
        )
        install_controller.delay(task_id)
        timeout_controller_install_task.apply_async(
            args=[task_id],
            countdown=CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
        )
        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="controller/uninstall")
    @HasPermission("cloud_region_node-Delete")
    def controller_uninstall(self, request):
        node_ids = [node["node_id"] for node in request.data.get("nodes", []) if node.get("node_id")]
        if node_ids:
            _, error_response = authorize_node_ids(request, node_ids)
            if error_response:
                return error_response
        task_id = InstallerService.uninstall_controller(
            request.data["cloud_region_id"],
            request.data["work_node"],
            request.data["nodes"],
            request.user.username,
            getattr(request.user, "domain", "domain.com"),
        )
        uninstall_controller.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="controller/retry")
    @HasPermission("cloud_region_node-Edit")
    def controller_retry(self, request):
        scope = resolve_current_team_data_scope(request)
        authorized_nodes = get_authorized_node_queryset(request)
        authorized_task_nodes = InstallerService.get_authorized_controller_task_nodes(
            request.data["task_id"],
            authorized_nodes=authorized_nodes,
            scope=scope,
        )
        requested_task_node_ids = request.data["task_node_ids"]
        if not isinstance(requested_task_node_ids, list):
            requested_task_node_ids = [requested_task_node_ids]
        authorized_task_node_ids = {str(task_node.id) for task_node in authorized_task_nodes}
        if not requested_task_node_ids or any(str(task_node_id) not in authorized_task_node_ids for task_node_id in requested_task_node_ids):
            return WebUtils.response_403("User does not have permission to retry this task node")

        retry_controller.delay(
            request.data["task_id"],
            requested_task_node_ids,
            password=request.data.get("password"),
            private_key=request.data.get("private_key"),
            passphrase=request.data.get("passphrase"),
        )
        return WebUtils.response_success()

    # 控制器手动安装
    @action(detail=False, methods=["post"], url_path="controller/manual_install")
    @HasPermission("cloud_region_node-Edit")
    def controller_manual_install(self, request):
        serializer = ControllerManualInstallRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        organization_error = _validate_install_target_organizations(request, data["nodes"])
        if organization_error:
            return organization_error
        cpu_architecture = data["cpu_architecture"]
        result = []
        for node in data["nodes"]:
            result.append(
                {
                    "cloud_region_id": data["cloud_region_id"],
                    "os": data["os"],
                    "cpu_architecture": cpu_architecture,
                    "package_id": data["package_id"],
                    "ip": node["ip"],
                    "node_id": node["node_id"],
                    "node_name": node.get("node_name", ""),
                    "organizations": node.get("organizations", []),
                }
            )
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path="controller/manual_install_status")
    @HasPermission("cloud_region_node-Edit")
    def controller_manual_install_status(self, request):
        node_ids = request.data.get("node_ids", [])
        data = InstallerService.get_manual_install_status(node_ids)
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
    @HasPermission("cloud_region_node-Edit")
    def controller_install_nodes(self, request, task_id):
        scope = resolve_current_team_data_scope(request)
        authorized_nodes = get_authorized_node_queryset(request)
        data = InstallerService.install_controller_nodes(
            task_id,
            authorized_nodes=authorized_nodes,
            scope=scope,
        )
        return WebUtils.response_success(data)

    # 采集器
    @action(detail=False, methods=["post"], url_path="collector/install")
    @HasPermission("cloud_region_node-OperateCollector")
    def collector_install(self, request):
        nodes = request.data.get("nodes", [])
        node_ids = [
            (node["node_id"] if isinstance(node, dict) else node) for node in nodes if (node.get("node_id") if isinstance(node, dict) else node)
        ]
        if node_ids:
            _, error_response = authorize_node_ids(request, node_ids)
            if error_response:
                return error_response
        task_id = InstallerService.install_collector(request.data["collector_package"], request.data["nodes"])
        install_collector.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(
        detail=False,
        methods=["post"],
        url_path="collector/install/(?P<task_id>[^/.]+)/nodes",
    )
    @HasPermission("cloud_region_node-OperateCollector")
    def collector_install_nodes(self, request, task_id):
        serializer = TaskNodesQuerySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)

        queryset = CollectorTaskNode.objects.filter(task_id=task_id).select_related("node").prefetch_related("node__nodeorganization_set")
        authorized_nodes = get_authorized_node_queryset(request)
        queryset = queryset.filter(node__in=authorized_nodes)
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

        summary_queryset = CollectorTaskNode.objects.filter(task_id=task_id).filter(node__in=authorized_nodes)
        summary = {
            "total": summary_queryset.count(),
            "waiting": summary_queryset.filter(status="waiting").count(),
            "running": summary_queryset.filter(status="running").count(),
            "success": summary_queryset.filter(status="success").count(),
            "error": summary_queryset.filter(status="error").count(),
            "timeout": summary_queryset.filter(result__overall_status="timeout").count(),
            "cancelled": summary_queryset.filter(result__overall_status="cancelled").count(),
        }

        return WebUtils.response_success(
            {
                "task_id": task_id,
                "status": project_task_status_from_summary(summary),
                "summary": summary,
                "items": data,
                "count": total,
                "page": page,
                "page_size": page_size,
            }
        )

    # 获取安装命令
    @action(detail=False, methods=["post"], url_path="get_install_command")
    @HasPermission("cloud_region_node-Edit")
    def get_install_command(self, request):
        serializer = InstallCommandRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        organization_error = _validate_install_target_organizations(request, [data])
        if organization_error:
            return organization_error
        node_error = _authorize_existing_install_nodes(request, [data["node_id"]])
        if node_error:
            return node_error
        data = InstallerService.get_install_command(
            request.user.username,
            data["ip"],
            data["node_id"],
            data["os"],
            data["package_id"],
            data["cloud_region_id"],
            data.get("organizations", []),
            data.get("node_name", ""),
            install_mode=InstallerService.MANUAL_INSTALL_MODE,
            cpu_architecture=data["cpu_architecture"],
        )
        return WebUtils.response_success(data)

    @action(detail=False, methods=["GET"], url_path="windows/download")
    def windows_download(self, request):
        serializer = InstallerArtifactQuerySerializer(data=request.query_params, context={"target_os": "windows"})
        serializer.is_valid(raise_exception=True)
        file, _ = InstallerService.download_windows_installer(serializer.validated_data.get("arch", ""))
        return WebUtils.response_file(file, InstallerConstants.WINDOWS_INSTALLER_FILENAME)

    @action(detail=False, methods=["GET"], url_path="linux/download")
    def linux_download(self, request):
        serializer = InstallerArtifactQuerySerializer(data=request.query_params, context={"target_os": "linux"})
        serializer.is_valid(raise_exception=True)
        file, _ = InstallerService.download_linux_installer(serializer.validated_data.get("arch", ""))
        return WebUtils.response_file(file, InstallerConstants.LINUX_INSTALLER_FILENAME)

    @action(detail=False, methods=["GET"], url_path="manifest")
    def manifest(self, request):
        return WebUtils.response_success(InstallerService.installer_manifest())

    @action(detail=False, methods=["GET"], url_path="metadata/(?P<target_os>[^/.]+)")
    def metadata(self, request, target_os):
        serializer = InstallerArtifactQuerySerializer(data=request.query_params, context={"target_os": target_os})
        serializer.is_valid(raise_exception=True)
        return WebUtils.response_success(InstallerService.installer_metadata(target_os, serializer.validated_data.get("arch", "")))
