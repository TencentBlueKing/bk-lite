"""监控统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.monitor.openapi_serializers import (
    MonitorInstanceQuerySerializer,
    MonitorMetricQuerySerializer,
    MonitorMetricRangeQuerySerializer,
    MonitorMetricValueQuerySerializer,
    MonitorObjectQuerySerializer,
    MonitorPolicyQuerySerializer,
)
from apps.monitor.openapi_service import (
    list_instances,
    list_metrics,
    list_objects,
    list_policies,
    query_metric_instant,
    query_metric_range,
)

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


@openapi_expose(
    path="monitor/metrics",
    method="GET",
    schema=MonitorMetricQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"分页查询监控对象的指标定义，不含查询语句（{_ORG_SCOPE}）",
)
def openapi_list_metrics(
    page=1,
    page_size=20,
    keyword="",
    monitor_object_id=None,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_metrics(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        monitor_object_id=monitor_object_id,
    )


@openapi_expose(
    path="monitor/metrics/instant",
    method="GET",
    schema=MonitorMetricValueQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"查询监控实例的指标当前值（{_ORG_SCOPE}）",
)
def openapi_query_metric_instant(instance_id, metric_id, *, team=None, user_info=None):
    del user_info
    return query_metric_instant(team=team, instance_id=instance_id, metric_id=metric_id)


@openapi_expose(
    path="monitor/metrics/range",
    method="GET",
    schema=MonitorMetricRangeQuerySerializer,
    inject="team_list_with_user",
    permission="view_list-View",
    permission_app="monitor",
    summary=f"查询监控实例的指标曲线，时间窗最长 6 小时（{_ORG_SCOPE}）",
)
def openapi_query_metric_range(
    instance_id,
    metric_id,
    start,
    end,
    step="5m",
    *,
    team=None,
    user_info=None,
):
    del user_info
    return query_metric_range(
        team=team,
        instance_id=instance_id,
        metric_id=metric_id,
        start=start,
        end=end,
        step=step,
    )
