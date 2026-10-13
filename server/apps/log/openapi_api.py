"""日志统一 OpenAPI 网关端点。"""

from apps.core.openapi.decorators import openapi_expose
from apps.log.openapi_serializers import LogGroupQuerySerializer, LogSearchQuerySerializer
from apps.log.openapi_service import list_groups, search_logs

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"


@openapi_expose(
    path="log/groups",
    method="GET",
    schema=LogGroupQuerySerializer,
    inject="team_list_with_user",
    permission="grouping-View",
    permission_app="log",
    summary=f"分页查询日志分组（{_ORG_SCOPE}）",
)
def openapi_list_groups(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    del user_info
    return list_groups(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="log/search",
    method="GET",
    schema=LogSearchQuerySerializer,
    inject="team_list_with_user",
    permission="search-View",
    permission_app="log",
    summary=f"检索日志，时间窗最长 1 小时，单次最多 100 条，正文截断（{_ORG_SCOPE}）",
)
def openapi_search_logs(log_group_id, start, end, query="*", limit=20, *, team=None, user_info=None):
    del user_info
    return search_logs(
        team=team,
        log_group_id=log_group_id,
        start=start,
        end=end,
        query=query,
        limit=limit,
    )
