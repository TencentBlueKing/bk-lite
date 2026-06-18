from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.rpc.node_mgmt import NodeMgmt
from apps.core.logger import monitor_logger as logger
from apps.monitor.utils.pagination import parse_page_params
from apps.monitor.utils.node_selector import merge_node_query_with_selector
from apps.core.utils.team_utils import get_current_team


def _build_actor_context(request):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


class NodeMgmtView(ViewSet):
    @action(methods=["post"], detail=False, url_path="nodes")
    def get_nodes(self, request):
        actor_context = _build_actor_context(request)
        orgs = {
            int(group["id"])
            for group in getattr(request.user, "group_list", [])
            if isinstance(group, dict) and group.get("name") == "OpsPilotGuest" and group.get("id") is not None
        }
        orgs.add(actor_context["current_team"])

        page, page_size = parse_page_params(request.data, default_page=1, default_page_size=10, allow_page_size_all=True)

        organization_ids = [] if request.user.is_superuser else list(orgs)
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
            },
        )
        monitor_plugin_id = request.data.get("monitor_plugin_id")
        if monitor_plugin_id and hasattr(InstanceConfigService, "_get_plugin_node_selector"):
            node_selector = InstanceConfigService._get_plugin_node_selector(monitor_plugin_id)
            query_data = merge_node_query_with_selector(query_data, node_selector)
        data = NodeMgmt().node_list(query_data)
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
