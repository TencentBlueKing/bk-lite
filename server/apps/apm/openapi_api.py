"""APM 统一 OpenAPI 网关端点。"""

from apps.apm.openapi_serializers import (
    ApmApplicationCreateSerializer,
    ApmApplicationPageResponseSerializer,
    ApmApplicationQuerySerializer,
    ApmApplicationResponseSerializer,
    ApmInstanceQuerySerializer,
    ApmIntegrationConfigSerializer,
    ApmIntegrationRegionQuerySerializer,
    ApmServiceMetricQuerySerializer,
    ApmServiceQuerySerializer,
    ApmTraceDetailQuerySerializer,
    ApmTraceQuerySerializer,
)
from apps.apm.openapi_service import (
    create_application,
    create_integration_config,
    get_trace,
    list_applications,
    list_instances,
    list_integration_regions,
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
    response_schema=ApmApplicationPageResponseSerializer,
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


@openapi_expose(
    path="apm/applications",
    method="POST",
    schema=ApmApplicationCreateSerializer,
    response_schema=ApmApplicationResponseSerializer,
    inject="team_list_with_user",
    permission="applications-Operate",
    permission_app="apm",
    summary=f"在接入页创建应用，并绑定令牌所在组织（{_ORG_SCOPE}）",
)
def openapi_create_application(application_id, name, description="", *, team=None, user_info=None):
    return create_application(
        team=team,
        user_info=user_info,
        application_id=application_id,
        name=name,
        description=description,
    )


@openapi_expose(
    path="apm/integration-regions",
    method="GET",
    schema=ApmIntegrationRegionQuerySerializer,
    inject="team_list_with_user",
    permission="integration_add-View",
    permission_app="apm",
    summary=f"查询接入页可选云区域（{_ORG_SCOPE}）",
)
def openapi_list_integration_regions(*, team=None, user_info=None):
    del user_info
    return list_integration_regions(team=team)


@openapi_expose(
    path="apm/integration-configs",
    method="POST",
    schema=ApmIntegrationConfigSerializer,
    inject="team_list_with_user",
    permission="integration_add-View",
    permission_app="apm",
    summary=f"按语言、运行时、服务名和云区域生成接入配置，不保存（{_ORG_SCOPE}）",
)
def openapi_create_integration_config(
    application_id,
    cloud_region_id,
    language,
    runtime,
    service_name,
    environment,
    service_version="",
    sample_rate=100,
    *,
    team=None,
    user_info=None,
):
    del user_info
    return create_integration_config(
        team=team,
        application_id=application_id,
        cloud_region_id=cloud_region_id,
        language=language,
        runtime=runtime,
        service_name=service_name,
        environment=environment,
        service_version=service_version,
        sample_rate=sample_rate,
    )
