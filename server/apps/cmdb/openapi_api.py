"""CMDB 统一 OpenAPI 网关端点。"""

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import VIEW
from apps.cmdb.open_api.auth import CMDBOpenAPIContext
from apps.cmdb.open_api.errors import CMDBOpenAPIError
from apps.cmdb.open_api.services import CMDBOpenAPIService, serialize_instance
from apps.cmdb.openapi_serializers import (
    CmdbInstanceAssociationCreateSerializer,
    CmdbInstanceAssociationDeleteSerializer,
    CmdbInstanceBatchCreateSerializer,
    CmdbInstanceBatchDeleteSerializer,
    CmdbInstanceBatchUpdateSerializer,
    CmdbInstanceCreateSerializer,
    CmdbInstanceKeySerializer,
    CmdbInstanceListSerializer,
    CmdbInstanceUpdateSerializer,
    CmdbModelIdSerializer,
    CmdbNoParamsSerializer,
)
from apps.core.openapi.decorators import openapi_expose

_ORG_SCOPE = "组织口径：API 令牌绑定组织精确匹配，不级联子组织"


def _run_cmdb_openapi(handler):
    try:
        return handler()
    except CMDBOpenAPIError as exc:
        return {"result": False, "message": exc.message}
    except ValidationError:
        return {"result": False, "message": "请求参数非法"}


def _service(team, user_info):
    return CMDBOpenAPIService(CMDBOpenAPIContext.from_gateway(user_info=user_info, team_ids=team))


def _uuid(value):
    return str(value)


@openapi_expose(
    path="cmdb/classifications",
    method="GET",
    schema=CmdbNoParamsSerializer,
    inject="team_list_with_user",
    permission="model_management-View",
    permission_app="cmdb",
    summary=f"查询可见模型分类（{_ORG_SCOPE}）",
)
def openapi_list_classifications(*, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).list_classifications())


@openapi_expose(
    path="cmdb/models",
    method="GET",
    schema=CmdbNoParamsSerializer,
    inject="team_list_with_user",
    permission="model_management-View",
    permission_app="cmdb",
    summary=f"查询可见模型列表（{_ORG_SCOPE}）",
)
def openapi_list_models(*, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).list_models())


@openapi_expose(
    path="cmdb/model",
    method="GET",
    schema=CmdbModelIdSerializer,
    inject="team_list_with_user",
    permission="model_management-View",
    permission_app="cmdb",
    summary=f"查询模型详情（{_ORG_SCOPE}）",
)
def openapi_get_model(model_id, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).get_model(model_id))


@openapi_expose(
    path="cmdb/model-attributes",
    method="GET",
    schema=CmdbModelIdSerializer,
    inject="team_list_with_user",
    permission="model_management-View",
    permission_app="cmdb",
    summary=f"查询模型属性定义（{_ORG_SCOPE}）",
)
def openapi_get_model_attributes(model_id, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).get_model_attrs(model_id))


@openapi_expose(
    path="cmdb/model-associations",
    method="GET",
    schema=CmdbModelIdSerializer,
    inject="team_list_with_user",
    permission="model_management-View",
    permission_app="cmdb",
    summary=f"查询模型关联定义（{_ORG_SCOPE}）",
)
def openapi_get_model_associations(model_id, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).get_model_associations(model_id))


@openapi_expose(
    path="cmdb/instances",
    method="GET",
    schema=CmdbInstanceListSerializer,
    inject="team_list_with_user",
    permission="asset_info-View",
    permission_app="cmdb",
    summary=f"分页查询实例（{_ORG_SCOPE}）",
)
def openapi_list_instances(model_id, page=1, page_size=20, order="", filters="[]", *, team=None, user_info=None):
    """由统一网关认证并注入不可伪造的单组织身份后，复用现有 OpenAPI 实例查询。"""

    def _list():
        return _service(team, user_info).list_instances(
            model_id,
            {
                "page": page,
                "page_size": page_size,
                "order": order or "",
                "filters": filters or "[]",
            },
        )

    return _run_cmdb_openapi(_list)


@openapi_expose(
    path="cmdb/instance-create",
    method="POST",
    schema=CmdbInstanceCreateSerializer,
    inject="team_list_with_user",
    permission="asset_info-Add",
    permission_app="cmdb",
    summary=f"创建实例，组织归属强制为令牌绑定组织（{_ORG_SCOPE}）",
)
def openapi_create_instance(model_id, attrs, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).create_instance(model_id, attrs))


@openapi_expose(
    path="cmdb/instance",
    method="GET",
    schema=CmdbInstanceKeySerializer,
    inject="team_list_with_user",
    permission="asset_info-View",
    permission_app="cmdb",
    summary=f"查询单个实例（跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_get_instance(model_id, inst_uuid, *, team=None, user_info=None):
    def _get():
        service = _service(team, user_info)
        service.context.require_feature("asset_info-View")
        return serialize_instance(service._get_instance(model_id, _uuid(inst_uuid), VIEW))

    return _run_cmdb_openapi(_get)


@openapi_expose(
    path="cmdb/instance",
    method="PUT",
    schema=CmdbInstanceUpdateSerializer,
    inject="team_list_with_user",
    permission="asset_info-Edit",
    permission_app="cmdb",
    summary=f"更新单个实例（原 REST PATCH；跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_update_instance(model_id, inst_uuid, attrs, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).update_instance(model_id, _uuid(inst_uuid), attrs))


@openapi_expose(
    path="cmdb/instance",
    method="DELETE",
    schema=CmdbInstanceKeySerializer,
    inject="team_list_with_user",
    permission="asset_info-Delete",
    permission_app="cmdb",
    summary=f"删除单个实例（跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_delete_instance(model_id, inst_uuid, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).delete_instance(model_id, _uuid(inst_uuid)))


@openapi_expose(
    path="cmdb/instance-batch-create",
    method="POST",
    schema=CmdbInstanceBatchCreateSerializer,
    inject="team_list_with_user",
    permission="asset_info-Add",
    permission_app="cmdb",
    summary=f"批量创建实例，组织归属强制为令牌绑定组织（{_ORG_SCOPE}）",
)
def openapi_batch_create_instances(model_id, items, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).batch_create_instances(model_id, {"items": items}))


@openapi_expose(
    path="cmdb/instance-batch-update",
    method="POST",
    schema=CmdbInstanceBatchUpdateSerializer,
    inject="team_list_with_user",
    permission="asset_info-Edit",
    permission_app="cmdb",
    summary=f"批量更新实例（跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_batch_update_instances(model_id, inst_uuids, update_data, *, team=None, user_info=None):
    return _run_cmdb_openapi(
        lambda: _service(team, user_info).batch_update_instances(
            model_id,
            {"inst_uuids": [_uuid(value) for value in inst_uuids], "update_data": update_data},
        )
    )


@openapi_expose(
    path="cmdb/instance-batch-delete",
    method="POST",
    schema=CmdbInstanceBatchDeleteSerializer,
    inject="team_list_with_user",
    permission="asset_info-Delete",
    permission_app="cmdb",
    summary=f"批量删除实例（跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_batch_delete_instances(model_id, inst_uuids, *, team=None, user_info=None):
    return _run_cmdb_openapi(
        lambda: _service(team, user_info).batch_delete_instances(
            model_id,
            {"inst_uuids": [_uuid(value) for value in inst_uuids]},
        )
    )


@openapi_expose(
    path="cmdb/instance-associations",
    method="GET",
    schema=CmdbInstanceKeySerializer,
    inject="team_list_with_user",
    permission="asset_info-View",
    permission_app="cmdb",
    summary=f"查询实例关联（跨组织按不存在处理，{_ORG_SCOPE}）",
)
def openapi_list_instance_associations(model_id, inst_uuid, *, team=None, user_info=None):
    return _run_cmdb_openapi(lambda: _service(team, user_info).list_instance_associations(model_id, _uuid(inst_uuid)))


@openapi_expose(
    path="cmdb/instance-associations",
    method="POST",
    schema=CmdbInstanceAssociationCreateSerializer,
    inject="team_list_with_user",
    permission="asset_info-Add Associate",
    permission_app="cmdb",
    summary=f"创建实例关联（源与目标均须属于绑定组织，{_ORG_SCOPE}）",
)
def openapi_create_instance_association(
    model_id,
    inst_uuid,
    model_asst_id,
    target_model_id,
    target_inst_uuid,
    *,
    team=None,
    user_info=None,
):
    return _run_cmdb_openapi(
        lambda: _service(team, user_info).create_instance_association(
            model_id,
            _uuid(inst_uuid),
            {
                "model_asst_id": model_asst_id,
                "target_model_id": target_model_id,
                "target_inst_uuid": _uuid(target_inst_uuid),
            },
        )
    )


@openapi_expose(
    path="cmdb/instance-association",
    method="DELETE",
    schema=CmdbInstanceAssociationDeleteSerializer,
    inject="team_list_with_user",
    permission="asset_info-Delete Associate",
    permission_app="cmdb",
    summary=f"删除实例关联（源与目标均须属于绑定组织，{_ORG_SCOPE}）",
)
def openapi_delete_instance_association(model_id, inst_uuid, dst_inst_uuid, model_asst_id, *, team=None, user_info=None):
    return _run_cmdb_openapi(
        lambda: _service(team, user_info).delete_instance_association(
            model_id,
            _uuid(inst_uuid),
            _uuid(dst_inst_uuid),
            model_asst_id,
        )
    )
