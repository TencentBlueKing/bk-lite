from typing import Any, cast

from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope, validate_assignable_organizations
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.models.installer import CollectorTaskNode
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.serializers.installer import (
    ControllerInstallRequestSerializer,
    ControllerManualInstallRequestSerializer,
    ControllerRetryRequestSerializer,
    ControllerUninstallRequestSerializer,
    InstallCommandRequestSerializer,
    InstallerArtifactQuerySerializer,
)
from apps.node_mgmt.serializers.node import TaskNodesQuerySerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.module_push import ModulePushService, build_module_push_actor_scope
from apps.node_mgmt.tasks.installer import (
    install_collector,
    install_controller,
    retry_controller,
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

        # 创建任务成功后按勾选目标 best-effort 推送；仅对已落库节点立刻推送。
        # 首次 sidecar 注册后的延迟推送尚未接线（见 DONE_WITH_CONCERNS）。
        push_targets = list(data.get("push_targets") or [])
        if push_targets and node_ids:
            existing_ids = set(Node.objects.filter(id__in=node_ids).values_list("id", flat=True))
            if existing_ids:
                actor_scope = build_module_push_actor_scope(request)
                for node_id in existing_ids:
                    ModulePushService.best_effort_push_node(
                        node_id,
                        targets=push_targets,
                        actor_scope=actor_scope,
                    )
            else:
                logger.info(
                    "[ModulePush] install created without existing nodes; deferred sidecar push not wired yet task_id=%s",
                    task_id,
                )

        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="controller/uninstall")
    @HasPermission("cloud_region_node-Delete")
    def controller_uninstall(self, request):
        requested_nodes = request.data.get("nodes", [])
        if not isinstance(requested_nodes, list) or not requested_nodes:
            return WebUtils.response_error(error_message="nodes is required")
        node_ids = [node.get("node_id") for node in requested_nodes if isinstance(node, dict) and node.get("node_id")]
        if len(node_ids) != len(requested_nodes):
            return WebUtils.response_error(error_message="node_id is required for every uninstall target")
        authorized_nodes, error_response = authorize_node_ids(request, node_ids)
        if error_response:
            return error_response

        authorized_map = {str(node.id): node for node in authorized_nodes}
        canonical_payload = {**request.data, "nodes": []}
        for requested_node in requested_nodes:
            actual_node = authorized_map[str(requested_node["node_id"])]
            canonical_payload["nodes"].append(
                {
                    **requested_node,
                    "node_id": str(actual_node.id),
                    "ip": actual_node.ip,
                    "node_name": actual_node.name,
                    "os": actual_node.operating_system,
                    "organizations": [relation.organization for relation in actual_node.nodeorganization_set.all()],
                }
            )

        serializer = ControllerUninstallRequestSerializer(data=canonical_payload)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        if any(node.cloud_region_id != data["cloud_region_id"] for node in authorized_nodes):
            return WebUtils.response_403("Uninstall target does not belong to the requested cloud region")
        task_id = InstallerService.uninstall_controller(
            data["cloud_region_id"],
            data["work_node"],
            data["nodes"],
            request.user.username,
            getattr(request.user, "domain", "domain.com"),
        )
        uninstall_controller.delay(task_id)
        return WebUtils.response_success(dict(task_id=task_id))

    @action(detail=False, methods=["post"], url_path="controller/retry")
    @HasPermission("cloud_region_node-Edit")
    def controller_retry(self, request):
        payload = request.data.copy()
        if "task_node_ids" in payload and not isinstance(payload["task_node_ids"], list):
            payload["task_node_ids"] = [payload["task_node_ids"]]
        serializer = ControllerRetryRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        scope = resolve_current_team_data_scope(request)
        task_node_ids = data["task_node_ids"]

        authorized_task_nodes = InstallerService.get_authorized_controller_task_node_queryset(
            data["task_id"],
            authorized_nodes=get_authorized_node_queryset(request),
            scope=scope,
            request_user=request.user,
        )
        selected_task_nodes = list(authorized_task_nodes.filter(id__in=task_node_ids))
        requested_ids = {str(task_node_id) for task_node_id in task_node_ids}
        authorized_ids = {str(task_node.id) for task_node in selected_task_nodes}
        if not requested_ids or authorized_ids != requested_ids:
            return WebUtils.response_403("User does not have permission to retry this controller installation")

        node_ids = [task_node.node_id for task_node in selected_task_nodes if task_node.node_id]
        if node_ids:
            _, error_response = authorize_node_ids(request, node_ids, required_permission="Operate")
            if error_response:
                return error_response

        if any(InstallerService.requires_manual_recovery(task_node.result) for task_node in selected_task_nodes):
            return WebUtils.response_error(error_message="Manual recovery is required before this node can be retried")

        retry_controller.delay(
            data["task_id"],
            task_node_ids,
            password=data.get("password"),
            port=data.get("port"),
            username=data.get("username"),
            private_key=data.get("private_key"),
            passphrase=data.get("passphrase"),
            winrm_scheme=data.get("winrm_scheme"),
            winrm_transport=data.get("winrm_transport"),
            winrm_cert_validation=data.get("winrm_cert_validation"),
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
        if not isinstance(node_ids, list) or any(type(node_id) is not str or not node_id.strip() for node_id in node_ids):
            return WebUtils.response_error(error_message="node_ids must be a list of non-empty strings")
        error_response = _authorize_existing_install_nodes(request, node_ids)
        if error_response:
            return error_response
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
