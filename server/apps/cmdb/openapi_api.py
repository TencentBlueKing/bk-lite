"""CMDB 统一 OpenAPI 网关端点。"""

from rest_framework.exceptions import ValidationError

from apps.cmdb.open_api.auth import CMDBOpenAPIContext
from apps.cmdb.open_api.errors import CMDBOpenAPIError
from apps.cmdb.open_api.services import CMDBOpenAPIService
from apps.cmdb.openapi_serializers import CmdbInstanceListSerializer
from apps.core.openapi.decorators import openapi_expose


def _run_cmdb_openapi(handler):
    try:
        return handler()
    except CMDBOpenAPIError as exc:
        return {"result": False, "message": exc.message}
    except ValidationError:
        return {"result": False, "message": "请求参数非法"}


@openapi_expose(
    path="cmdb/instances",
    method="GET",
    schema=CmdbInstanceListSerializer,
    inject="team_list_with_user",
    permission="asset_info-View",
    permission_app="cmdb",
    summary="分页查询实例（组织口径：API 令牌绑定组织精确匹配，不级联子组织）",
)
def openapi_list_instances(model_id, page=1, page_size=20, order="", filters="[]", *, team=None, user_info=None):
    """由统一网关认证并注入不可伪造的单组织身份后，复用现有 OpenAPI 实例查询。"""

    def _list():
        context = CMDBOpenAPIContext.from_gateway(user_info=user_info, team_ids=team)
        return CMDBOpenAPIService(context).list_instances(
            model_id,
            {
                "page": page,
                "page_size": page_size,
                "order": order or "",
                "filters": filters or "[]",
            },
        )

    return _run_cmdb_openapi(_list)
