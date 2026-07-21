from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.services.cloud_region_receiver import CloudRegionReceiverService
from apps.rpc.node_mgmt import NodeMgmt


class NodeViewSet(ViewSet):
    @action(methods=["post"], detail=False, url_path="nodes")
    def get_nodes(self, request):
        try:
            scope = LogAccessScopeService.get_data_scope(request)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)
        organization_ids = list(scope.data_team_ids)
        data = NodeMgmt().node_list(
            dict(
                cloud_region_id=request.data.get("cloud_region_id", 1),
                organization_ids=organization_ids,
                name=request.data.get("name"),
                ip=request.data.get("ip"),
                os=request.data.get("os"),
                page=request.data.get("page", 1),
                page_size=request.data.get("page_size", 10),
                is_active=request.data.get("is_active"),
                is_manual=request.data.get("is_manual"),
                is_container=request.data.get("is_container"),
                permission_data={
                    "username": request.user.username,
                    "domain": request.user.domain,
                    "current_team": scope.current_team,
                    "include_children": scope.include_children,
                    "is_superuser": scope.is_superuser,
                },
            )
        )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="cloud_region_proxy_address")
    def get_cloud_region_proxy_address(self, request):
        cloud_region_id = request.data.get("cloud_region_id")
        try:
            scope = LogAccessScopeService.get_data_scope(request)
        except ValueError as exc:
            return WebUtils.response_error(error_message=str(exc), status_code=403)
        organization_ids = list(scope.data_team_ids)
        proxy_address = CloudRegionReceiverService.resolve(NodeMgmt(), cloud_region_id, organization_ids)
        return WebUtils.response_success({"proxy_address": proxy_address or ""})
