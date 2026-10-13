"""APM 统一 OpenAPI 网关端点。"""

from apps.apm.openapi_serializers import (
    ApmApplicationQuerySerializer,
    ApmInstanceQuerySerializer,
    ApmServiceQuerySerializer,
)
from apps.apm.openapi_service import list_applications, list_instances, list_services
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
