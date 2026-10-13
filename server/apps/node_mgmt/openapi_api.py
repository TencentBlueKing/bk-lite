"""节点管理统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.node_mgmt.openapi_serializers import (
    NodeCloudRegionQuerySerializer,
    NodeDetailQuerySerializer,
    NodeListQuerySerializer,
)
from apps.node_mgmt.openapi_service import get_node, list_cloud_regions, list_nodes

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"
_CATALOG_SCOPE = "云区域是平台目录，不按组织拆分；调用仍须绑定组织"
_STATUS_SCOPE = "在线状态与节点列表一致，按 60 秒内心跳判断；采集器状态与列表展示口径一致"


@openapi_expose(
    path="node/cloud-regions",
    method="GET",
    schema=NodeCloudRegionQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_list-View",
    permission_app="node",
    summary=f"分页查询云区域（{_CATALOG_SCOPE}）",
)
def openapi_list_cloud_regions(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_cloud_regions(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="node/nodes",
    method="GET",
    schema=NodeListQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-View",
    permission_app="node",
    summary=f"分页查询节点及采集器、控制器状态（{_ORG_SCOPE}；{_STATUS_SCOPE}）",
)
def openapi_list_nodes(
    page=1,
    page_size=20,
    keyword="",
    cloud_region_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_nodes(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        cloud_region_id=cloud_region_id,
    )


@openapi_expose(
    path="node/nodes/detail",
    method="GET",
    schema=NodeDetailQuerySerializer,
    inject="team_list_with_user",
    permission="cloud_region_node-View",
    permission_app="node",
    summary=f"查询单个节点（跨组织按不存在处理，{_ORG_SCOPE}；{_STATUS_SCOPE}）",
)
def openapi_get_node(node_id, *, team=None, user_info=None):
    del user_info
    return get_node(team=team, node_id=node_id)
