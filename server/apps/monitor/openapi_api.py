"""监控统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.monitor.openapi_serializers import (
    MonitorInstanceQuerySerializer,
    MonitorObjectQuerySerializer,
    MonitorPolicyQuerySerializer,
)
from apps.monitor.openapi_service import list_instances, list_objects, list_policies

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"
_CATALOG_SCOPE = "监控对象是平台目录，各组织看到同一份可见对象；调用仍须绑定组织"


@openapi_expose(
    path="monitor/objects",
    method="GET",
    schema=MonitorObjectQuerySerializer,
    inject="team_list_with_user",
    permission="object-View",
    permission_app="monitor",
    summary=f"分页查询可见监控对象（{_CATALOG_SCOPE}）",
)
def openapi_list_objects(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_objects(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="monitor/instances",
    method="GET",
    schema=MonitorInstanceQuerySerializer,
    inject="team_list_with_user",
    permission="asset-View",
    permission_app="monitor",
    summary=f"分页查询监控实例（{_ORG_SCOPE}）",
)
def openapi_list_instances(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_instances(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )


@openapi_expose(
    path="monitor/policies",
    method="GET",
    schema=MonitorPolicyQuerySerializer,
    inject="team_list_with_user",
    permission="strategy_list-View",
    permission_app="monitor",
    summary=f"分页查询监控策略，不含策略组内规则（{_ORG_SCOPE}）",
)
def openapi_list_policies(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_policies(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )
