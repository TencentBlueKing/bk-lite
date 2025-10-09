from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.core.utils.web_utils import WebUtils
from apps.rpc.node_mgmt import NodeMgmt


class NodeViewSet(ViewSet):
    @action(methods=['post'], detail=False, url_path='nodes')
    def get_nodes(self, request):
        organization_ids = [] if request.user.is_superuser else [i["id"] for i in request.user.group_list]
        data = NodeMgmt().node_list(dict(
            cloud_region_id=request.data.get("cloud_region_id", 1),
            organization_ids=organization_ids,
            name=request.data.get("name"),
            ip=request.data.get("ip"),
            os=request.data.get("os"),
            page=request.data.get("page", 1),
            page_size=request.data.get("page_size", 10),
            is_active=request.data.get("is_active"),
            permission_data={
                "username": request.user.username,
                "domain": request.user.domain,
                "current_team": request.COOKIES.get("current_team"),
                }
        ))
        return WebUtils.response_success(data)
