from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.logger import monitor_logger as logger
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.monitor.models import MonitorPlugin
from apps.monitor.services.host_deployment import HostDeploymentStatus
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.utils.node_selector import merge_node_query_with_selector
from apps.monitor.utils.pagination import parse_page_params
from apps.rpc.node_mgmt import NodeMgmt


def _build_actor_context(request):
    scope = resolve_current_team_data_scope(request)

    return {
        "username": scope.username,
        "domain": scope.domain,
        "current_team": scope.current_team,
        "include_children": scope.include_children,
        "is_superuser": scope.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
        "data_scope": scope,
        "request": request,
    }


class NodeMgmtView(ViewSet):
    @action(methods=["post"], detail=False, url_path="nodes")
    def get_nodes(self, request):
        actor_context = _build_actor_context(request)
        page, page_size = parse_page_params(request.data, default_page=1, default_page_size=10, allow_page_size_all=True)

        organization_ids = sorted(actor_context["data_scope"].data_team_ids)
        query_data = dict(
            cloud_region_id=request.data.get("cloud_region_id", 1),
            organization_ids=organization_ids,
            name=request.data.get("name"),
            ip=request.data.get("ip"),
            os=request.data.get("os"),
            page=page,
            page_size=page_size,
            is_active=request.data.get("is_active"),
            is_manual=request.data.get("is_manual"),
            is_container=request.data.get("is_container"),
            permission_data={
                "username": request.user.username,
                "domain": request.user.domain,
                "current_team": actor_context["current_team"],
                "include_children": actor_context["include_children"],
            },
        )
        monitor_plugin_id = request.data.get("monitor_plugin_id")
        if monitor_plugin_id and hasattr(InstanceConfigService, "_get_plugin_node_selector"):
            node_selector = InstanceConfigService._get_plugin_node_selector(monitor_plugin_id)
            query_data = merge_node_query_with_selector(query_data, node_selector)
        data = NodeMgmt().node_list(query_data)
        plugin = (
            MonitorPlugin.objects.filter(id=monitor_plugin_id)
            .prefetch_related("monitor_object")
            .first()
            if monitor_plugin_id
            else None
        )
        is_host_monitoring_plugin = bool(
            plugin
            and any(
                HostDeploymentStatus.applies_to(obj.name, plugin.collector, plugin.collect_type)
                for obj in plugin.monitor_object.all()
            )
        )
        if is_host_monitoring_plugin:
            nodes = data.get("nodes", [])
            configured_node_ids = HostDeploymentStatus().get_configured_node_ids(
                [node.get("id") for node in nodes]
            )
            data["nodes"] = [
                {
                    **node,
                    "deployment_state": "configured" if str(node.get("id")) in configured_node_ids else "available",
                }
                for node in nodes
            ]
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="batch_setting_node_child_config")
    def batch_setting_node_child_config(self, request):
        actor_context = _build_actor_context(request)
        logger.debug(
            "batch_setting_node_child_config called by user=%s, current_team=%s",
            request.user.username,
            get_current_team(request),
        )
        InstanceConfigService.create_monitor_instance_by_node_mgmt(request.data, actor_context)
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="get_instance_asso_config")
    def get_instance_child_config(self, request):
        actor_context = _build_actor_context(request)
        data = InstanceConfigService.get_instance_configs(
            request.data["instance_id"],
            actor_context,
            monitor_plugin_id=request.data.get("monitor_plugin_id"),
            collector=request.data.get("collector"),
            collect_type=request.data.get("collect_type"),
        )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="get_config_content")
    def get_config_content(self, request):
        actor_context = _build_actor_context(request)
        result = InstanceConfigService.get_config_content(request.data["ids"], actor_context)
        return WebUtils.response_success(result)

    @action(methods=["post"], detail=False, url_path="update_instance_collect_config")
    def update_instance_collect_config(self, request):
        actor_context = _build_actor_context(request)
        InstanceConfigService.update_instance_config(request.data.get("child"), request.data.get("base"), actor_context)
        return WebUtils.response_success()
