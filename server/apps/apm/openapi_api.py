"""APM 统一 OpenAPI 网关端点。"""

from apps.apm.openapi_serializers import (
    ApmApplicationQuerySerializer,
    ApmInstanceQuerySerializer,
    ApmServiceMetricQuerySerializer,
    ApmServiceQuerySerializer,
    ApmTraceDetailQuerySerializer,
    ApmTraceQuerySerializer,
)
from apps.apm.openapi_service import (
    get_trace,
    list_applications,
    list_instances,
    list_services,
    list_traces,
    query_service_metrics,
)
from apps.core.openapi.decorators import openapi_expose

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"


@openapi_expose(
    path="apm/applications",
    method="GET",
    schema=ApmApplicationQuerySerializer,
    inject="team_list_with_user",
    permission="applications-View",
    permission_app="apm",
    summary=f"分页查询 APM 应用，不含内置应用（{_ORG_SCOPE}）",
)
def openapi_list_applications(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_applications(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="apm/services",
    method="GET",
    schema=ApmServiceQuerySerializer,
    inject="team_list_with_user",
    permission="services-View",
    permission_app="apm",
    summary=f"分页查询 APM 服务（{_ORG_SCOPE}）",
)
def openapi_list_services(
    page=1,
    page_size=20,
    keyword="",
    application_id="",
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_services(
        team=team,
        page=page,
        page_size=page_size,
        keyword=keyword,
        application_id=application_id,
    )


@openapi_expose(
    path="apm/instances",
    method="GET",
    schema=ApmInstanceQuerySerializer,
    inject="team_list_with_user",
    permission="integration_instances-View",
    permission_app="apm",
    summary=f"分页查询 APM 服务实例（{_ORG_SCOPE}）",
)
def openapi_list_instances(
    page=1,
    page_size=20,
    keyword="",
    application_id="",
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
        application_id=application_id,
    )


@openapi_expose(
    path="apm/services/metrics",
    method="GET",
    schema=ApmServiceMetricQuerySerializer,
    inject="team_list_with_user",
    permission="services-View",
    permission_app="apm",
    summary=f"查询服务的请求量、错误率和耗时，时间窗最长 7 天（{_ORG_SCOPE}）",
)
def openapi_query_service_metrics(service_id, start, end, environment="", *, team=None, user_info=None):
    del user_info
    return query_service_metrics(
        team=team,
        service_id=service_id,
        start=start,
        end=end,
        environment=environment,
    )


@openapi_expose(
    path="apm/traces",
    method="GET",
    schema=ApmTraceQuerySerializer,
    inject="team_list_with_user",
    permission="traces-View",
    permission_app="apm",
    summary=f"查询调用摘要，时间窗最长 1 小时，单次最多 100 条（{_ORG_SCOPE}）",
)
def openapi_list_traces(
    start,
    end,
    service_id="",
    status=None,
    limit=20,
    cursor="",
    *,
    team=None,
    user_info=None,
):
    del user_info
    return list_traces(
        team=team,
        start=start,
        end=end,
        service_id=service_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )


@openapi_expose(
    path="apm/traces/detail",
    method="GET",
    schema=ApmTraceDetailQuerySerializer,
    inject="team_list_with_user",
    permission="traces-View",
    permission_app="apm",
    summary=f"查询单条调用，跨组织按不存在处理（{_ORG_SCOPE}）",
)
def openapi_get_trace(trace_id, *, team=None, user_info=None):
    del user_info
    return get_trace(team=team, trace_id=trace_id)
