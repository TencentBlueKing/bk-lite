"""CMDB 模型视图覆盖测试（patch ModelManage + 权限）。

对照 spec/prd/CMDB·模型管理：模型增删改查、模型关联、自动关联规则、属性增删改查、
唯一校验规则、模型复制、关联类型、导入导出配置等接口层逻辑与权限校验。
"""

import importlib
import io
import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.model import ModelManage
from apps.cmdb.views.model import ModelViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

VIEWS = "apps.cmdb.views.model"

try:
    __import__("apps.cmdb.enterprise.services.custom_reporting_model_service", fromlist=["CustomReportingModelService"])
    _ENTERPRISE_MODEL_SERVICE_MISSING = False
except ModuleNotFoundError as exc:
    if exc.name not in {
        "apps.cmdb.enterprise",
        "apps.cmdb.enterprise.services",
        "apps.cmdb.enterprise.services.custom_reporting_model_service",
    }:
        raise
    _ENTERPRISE_MODEL_SERVICE_MISSING = True

requires_enterprise_model_service = pytest.mark.skipif(
    _ENTERPRISE_MODEL_SERVICE_MISSING,
    reason="enterprise custom reporting unavailable",
)


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.locale = "zh-Hans"
    return u


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **k: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", lambda **k: True)
    monkeypatch.setattr(f"{VIEWS}.get_default_group_id", lambda: [1])
    monkeypatch.setattr(f"{VIEWS}.ModelViewSet.organizations", lambda self, r, m: [1])
    monkeypatch.setattr(f"{VIEWS}.create_change_record", lambda **k: None)


def _req(method, user, data=None, query="", files=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/" + (f"?{query}" if query else "")
    if files is not None:
        request = fn(path, data=files, format="multipart")
    elif data is None:
        request = fn(path)
    else:
        request = fn(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# model_add_permission（纯函数）
# --------------------------------------------------------------------------


def test_model_add_permission_default_group_view():
    models = [{"model_id": "host", "group": [1]}]
    ModelViewSet.model_add_permission(models, permission_instances_map={}, default_group=1)
    assert "View" in models[0]["permission"]


def test_model_add_permission_by_model_id():
    models = [{"model_id": "host", "group": [6]}]
    pmap = {6: {"permission_instances_map": {"host": ["View"]}}}
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert models[0]["permission"] == ["View"]


def test_model_add_permission_same_model_id_other_org_denied():
    models = [{"model_id": "host", "group": [9]}]
    pmap = {6: {"permission_instances_map": {"host": ["View"]}}}
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert models[0]["permission"] == []


def test_model_add_permission_same_model_id_ignores_other_org_permissions():
    models = [{"model_id": "host", "group": [6]}]
    pmap = {
        6: {"permission_instances_map": {"host": ["View"]}},
        8: {"permission_instances_map": {"host": ["Operate"]}},
    }
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert models[0]["permission"] == ["View"]


def test_model_add_permission_merges_default_group_and_same_org_permission():
    models = [{"model_id": "host", "group": [1, 6]}]
    pmap = {6: {"permission_instances_map": {"host": ["Operate"]}}}
    ModelViewSet.model_add_permission(models, permission_instances_map=pmap, default_group=1)
    assert set(models[0]["permission"]) == {"View", "Operate"}


# --------------------------------------------------------------------------
# get_model_info
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_model_info_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda model_id: {})
    response = ModelViewSet.as_view({"get": "get_model_info"})(_req("get", superuser), model_id="host")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_get_model_info_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "model_name": "主机", "group": [1]},
    )
    response = ModelViewSet.as_view({"get": "get_model_info"})(_req("get", superuser), model_id="host")
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["model_id"] == "host"


@pytest.mark.django_db
def test_get_model_info_denied_when_name_permission_only_exists_in_other_org(superuser, monkeypatch):
    permission_module = importlib.reload(importlib.import_module("apps.cmdb.utils.permission_util"))

    superuser.group_list = [{"id": 9}]
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": "host", "model_name": "主机", "group": [9]},
    )
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission",
        permission_module.CmdbRulesFormatUtil.has_object_permission,
    )
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *a, **k: {6: {"permission_instances_map": {"host": ["View"]}, "inst_names": ["host"]}},
    )
    request = _req("get", superuser)
    request.COOKIES["current_team"] = "9"
    response = ModelViewSet.as_view({"get": "get_model_info"})(request, model_id="host")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------
# create / list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_invalid_id(superuser):
    response = ModelViewSet.as_view({"post": "create"})(_req("post", superuser, data={"model_id": "1bad!"}))
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_create_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.create_model",
        lambda data, username="admin": {"model_id": data["model_id"]},
    )
    response = ModelViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"model_id": "host", "model_name": "主机"})
    )
    assert _body(response)["data"]["model_id"] == "host"


@requires_enterprise_model_service
def test_bootstrap_custom_reporting_model_creates_missing_identity_attrs(monkeypatch):
    created_models = []
    created_attrs = []

    monkeypatch.setattr(
        ModelManage,
        "create_model",
        lambda data, username="admin": created_models.append((dict(data), username))
        or {
            "model_id": data["model_id"],
            "model_name": data["model_name"],
            "classification_id": data["classification_id"],
            "group": data["group"],
        },
    )
    monkeypatch.setattr(
        ModelManage,
        "create_model_attr",
        lambda model_id, attr_info, username="admin": created_attrs.append((model_id, dict(attr_info), username))
        or attr_info,
    )

    result = ModelManage.bootstrap_custom_reporting_model(
        {
            "model_id": "report_asset",
            "model_name": "上报资产",
            "classification_id": "server",
            "identity_keys": ["asset_code", "inst_name", "asset_code"],
        },
        team=[1],
        username="alice",
    )

    assert created_models == [
        (
            {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [1],
            },
            "alice",
        )
    ]
    assert created_attrs == [
        (
            "report_asset",
            {
                "attr_id": "asset_code",
                "attr_name": "asset_code",
                "attr_group": "default",
                "attr_type": "str",
                "is_only": True,
                "is_required": False,
                "editable": True,
                "option": {},
                "user_prompt": "",
                "default_value": [],
            },
            "alice",
        )
    ]
    assert result == {
        "model_id": "report_asset",
        "model_name": "上报资产",
        "classification_id": "server",
        "group": [1],
        "identity_keys": ["asset_code", "inst_name"],
    }


@requires_enterprise_model_service
def test_bootstrap_custom_reporting_model_ignores_caller_supplied_group(monkeypatch):
    created_models = []

    monkeypatch.setattr(
        ModelManage,
        "create_model",
        lambda data, username="admin": created_models.append((dict(data), username))
        or {
            "model_id": data["model_id"],
            "model_name": data["model_name"],
            "classification_id": data["classification_id"],
            "group": data["group"],
        },
    )
    monkeypatch.setattr(
        ModelManage,
        "create_model_attr",
        lambda model_id, attr_info, username="admin": attr_info,
    )

    result = ModelManage.bootstrap_custom_reporting_model(
        {
            "model_id": "report_asset",
            "model_name": "上报资产",
            "classification_id": "server",
            "group": [999],
            "identity_keys": ["inst_name"],
        },
        team=[1],
        username="alice",
    )

    assert created_models == [
        (
            {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [1],
            },
            "alice",
        )
    ]
    assert result["group"] == [1]


@requires_enterprise_model_service
def test_sync_custom_reporting_model_group_updates_existing_model_group(monkeypatch):
    searched_model_ids = []
    update_calls = []

    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: searched_model_ids.append(model_id)
        or {
            "_id": 7,
            "model_id": model_id,
            "model_name": "上报资产",
            "classification_id": "server",
            "group": [1],
        },
    )
    monkeypatch.setattr(
        ModelManage,
        "update_model",
        lambda model_pk, data: update_calls.append((model_pk, dict(data)))
        or {
            "_id": model_pk,
            "model_id": data["model_id"],
            "model_name": data["model_name"],
            "classification_id": data["classification_id"],
            "group": data["group"],
        },
    )

    result = ModelManage.sync_custom_reporting_model_group(
        {
            "model_id": "report_asset",
            "model_name": "旧名称",
            "classification_id": "old",
            "identity_keys": ["asset_code"],
        },
        team=[2],
        username="alice",
    )

    assert searched_model_ids == ["report_asset"]
    assert update_calls == [
        (
            7,
            {
                "model_id": "report_asset",
                "model_name": "上报资产",
                "classification_id": "server",
                "group": [2],
            },
        )
    ]
    assert result == {
        "model_id": "report_asset",
        "model_name": "上报资产",
        "classification_id": "server",
        "group": [2],
        "identity_keys": ["asset_code"],
    }


@pytest.mark.django_db
def test_list_models(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model",
        lambda language=None, permissions_map=None, **kwargs: [{"model_id": "host", "group": [1]}],
    )
    response = ModelViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert _body(response)["data"][0]["model_id"] == "host"


# --------------------------------------------------------------------------
# destroy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_destroy_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda pk: {})
    response = ModelViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="host")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_no_org(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info", lambda pk: {"model_id": "host", "group": [1], "_id": 1}
    )
    monkeypatch.setattr(f"{VIEWS}.ModelViewSet.organizations", lambda self, r, m: [])
    response = ModelViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="host")
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_destroy_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda pk: {"model_id": "host", "model_name": "主机", "group": [1], "_id": 7},
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.check_model_exist_association", lambda pk: None)
    monkeypatch.setattr(f"{VIEWS}.ModelManage.check_model_exist_inst", lambda pk: None)
    monkeypatch.setattr(f"{VIEWS}.ModelManage.delete_model", lambda _id: None)
    response = ModelViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="host")
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# update
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_update_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda pk: {})
    response = ModelViewSet.as_view({"put": "update"})(_req("put", superuser, data={}), pk="host")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_update_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda pk: {"model_id": "host", "model_name": "主机", "group": [1], "_id": 7},
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model", lambda _id, data: {"_id": _id, **data})
    response = ModelViewSet.as_view({"put": "update"})(
        _req("put", superuser, data={"model_name": "主机2"}), pk="host"
    )
    assert _body(response)["data"]["model_name"] == "主机2"


# --------------------------------------------------------------------------
# model_association_create
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_association_create_src_missing(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {})
    response = ModelViewSet.as_view({"post": "model_association_create"})(
        _req("post", superuser, data={"src_model_id": "a", "dst_model_id": "b", "asst_id": "c"})
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_model_association_create_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1], "_id": mid}
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_create", lambda **k: {"_id": 100})
    response = ModelViewSet.as_view({"post": "model_association_create"})(
        _req("post", superuser, data={"src_model_id": "a", "dst_model_id": "b", "asst_id": "c"})
    )
    assert _body(response)["data"]["_id"] == 100


# --------------------------------------------------------------------------
# model_association_delete / batch_delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_association_delete_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_info_search", lambda aid: {})
    response = ModelViewSet.as_view({"delete": "model_association_delete"})(
        _req("delete", superuser), model_asst_id="a_b_c"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_model_association_delete_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.model_association_info_search",
        lambda aid: {"_id": 1, "src_model_id": "a", "dst_model_id": "b"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1], "_id": mid}
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_delete", lambda _id: None)
    response = ModelViewSet.as_view({"delete": "model_association_delete"})(
        _req("delete", superuser), model_asst_id="a_b_c"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_model_association_batch_delete_empty(superuser):
    response = ModelViewSet.as_view({"post": "model_association_batch_delete"})(
        _req("post", superuser, data={"model_asst_ids": []})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_model_association_batch_delete_too_many(superuser):
    response = ModelViewSet.as_view({"post": "model_association_batch_delete"})(
        _req("post", superuser, data={"model_asst_ids": [f"a{i}" for i in range(201)]})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_model_association_batch_delete_mixed(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.model_association_info_search",
        lambda aid: {"_id": 1, "src_model_id": "a", "dst_model_id": "b"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1], "_id": mid}
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_delete", lambda _id: None)
    response = ModelViewSet.as_view({"post": "model_association_batch_delete"})(
        _req("post", superuser, data={"model_asst_ids": ["a_b_c", "", 123]})
    )
    data = _body(response)["data"]
    assert data["success_count"] == 1
    assert data["failed_count"] == 2


# --------------------------------------------------------------------------
# model_association_list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_association_list_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]}
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.model_association_search", lambda mid: [{"_id": 1}])
    response = ModelViewSet.as_view({"get": "model_association_list"})(_req("get", superuser), model_id="host")
    assert _body(response)["data"][0]["_id"] == 1


# --------------------------------------------------------------------------
# model_auto_association_rules（GET / POST）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_auto_association_rules_get(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.get_model_auto_relation_rules", lambda mid: [{"rule_id": "r1"}])
    response = ModelViewSet.as_view({"get": "model_auto_association_rules"})(_req("get", superuser), model_id="host")
    assert _body(response)["data"][0]["rule_id"] == "r1"


@pytest.mark.django_db
def test_auto_association_rules_post_missing_asst(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    response = ModelViewSet.as_view({"post": "model_auto_association_rules"})(
        _req("post", superuser, data={}), model_id="host"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_auto_association_rules_post_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.save_model_auto_relation_rule", lambda *a, **k: {"rule_id": "r2"})
    response = ModelViewSet.as_view({"post": "model_auto_association_rules"})(
        _req("post", superuser, data={"model_asst_id": "a_b_c"}), model_id="host"
    )
    assert _body(response)["data"]["rule_id"] == "r2"


@pytest.mark.django_db
def test_auto_association_rule_detail_put(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model_auto_relation_rule", lambda *a, **k: {"ok": True})
    response = ModelViewSet.as_view({"put": "model_auto_association_rule_detail"})(
        _req("put", superuser, data={}), model_id="host", model_asst_id="a", rule_id="r1"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_auto_association_rule_detail_delete(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.delete_model_auto_relation_rule", lambda *a, **k: None)
    response = ModelViewSet.as_view({"delete": "model_auto_association_rule_detail"})(
        _req("delete", superuser), model_id="host", model_asst_id="a", rule_id="r1"
    )
    assert _body(response)["data"] is True


@pytest.mark.django_db
def test_auto_association_rule_detail_error(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})

    def _raise(*a, **k):
        raise BaseAppException("规则冲突")

    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model_auto_relation_rule", _raise)
    response = ModelViewSet.as_view({"put": "model_auto_association_rule_detail"})(
        _req("put", superuser, data={}), model_id="host", model_asst_id="a", rule_id="r1"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------
# model_attr_create / update / delete / list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_attr_create_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.create_model_attr", lambda *a, **k: {"attr_id": "ip"})
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=[])
    response = ModelViewSet.as_view({"post": "model_attr_create"})(
        _req("post", superuser, data={"attr_id": "ip", "attr_group": "网络"}), model_id="host"
    )
    assert _body(response)["data"]["attr_id"] == "ip"
    fg = FieldGroup.objects.get(model_id="host", group_name="网络")
    assert "ip" in fg.attr_orders


@pytest.mark.django_db
def test_model_attr_update_enum(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model_attr", lambda *a, **k: {"attr_id": "status"})
    called = {}
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.update_enum_instances_display",
        lambda mid, aid, opts: called.setdefault("hit", True),
    )
    response = ModelViewSet.as_view({"put": "model_attr_update"})(
        _req("put", superuser, data={"attr_id": "status", "attr_type": "enum", "option": []}), model_id="host"
    )
    assert response.status_code == status.HTTP_200_OK
    assert called.get("hit") is True


@pytest.mark.django_db
def test_model_attr_delete_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.delete_model_attr", lambda *a, **k: {"deleted": True})
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    response = ModelViewSet.as_view({"delete": "model_attr_delete"})(
        _req("delete", superuser), model_id="host", attr_id="ip"
    )
    assert response.status_code == status.HTTP_200_OK
    fg = FieldGroup.objects.get(model_id="host", group_name="网络")
    assert "ip" not in fg.attr_orders


@pytest.mark.django_db
def test_model_attr_list(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_attr",
        lambda mid, locale: [{"attr_id": "ip"}, {"attr_id": "x", "is_display_field": True}],
    )
    response = ModelViewSet.as_view({"get": "model_attr_list"})(_req("get", superuser), model_id="host")
    data = _body(response)["data"]
    assert [a["attr_id"] for a in data] == ["ip"]  # display 字段被过滤


# --------------------------------------------------------------------------
# unique_rules
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_unique_rules_get(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.get_model_unique_rules", lambda mid, rid: [{"rule_id": "u1"}])
    response = ModelViewSet.as_view({"get": "model_unique_rules"})(_req("get", superuser), model_id="host")
    assert _body(response)["data"][0]["rule_id"] == "u1"


@pytest.mark.django_db
def test_unique_rules_post(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.create_model_unique_rule", lambda *a, **k: {"rule_id": "u2"})
    response = ModelViewSet.as_view({"post": "model_unique_rules"})(
        _req("post", superuser, data={"attrs": []}), model_id="host"
    )
    assert _body(response)["data"]["rule_id"] == "u2"


@pytest.mark.django_db
def test_unique_rule_detail_put(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.update_model_unique_rule", lambda *a, **k: {"ok": True})
    response = ModelViewSet.as_view({"put": "model_unique_rule_detail"})(
        _req("put", superuser, data={}), model_id="host", rule_id="u1"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_unique_rule_detail_delete(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.delete_model_unique_rule", lambda *a, **k: {"ok": True})
    response = ModelViewSet.as_view({"delete": "model_unique_rule_detail"})(
        _req("delete", superuser), model_id="host", rule_id="u1"
    )
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# model_copy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_copy_validations(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    view = ModelViewSet.as_view({"post": "model_copy"})
    # 缺 new_model_id
    r1 = view(_req("post", superuser, data={}), model_id="host")
    assert r1.status_code == status.HTTP_400_BAD_REQUEST
    # 非法 new_model_id
    r2 = view(_req("post", superuser, data={"new_model_id": "1bad!"}), model_id="host")
    assert r2.status_code == status.HTTP_400_BAD_REQUEST
    # 缺 new_model_name
    r3 = view(_req("post", superuser, data={"new_model_id": "host2"}), model_id="host")
    assert r3.status_code == status.HTTP_400_BAD_REQUEST
    # 未选复制方式
    r4 = view(_req("post", superuser, data={"new_model_id": "host2", "new_model_name": "主机2"}), model_id="host")
    assert r4.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_model_copy_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_info", lambda mid: {"model_id": mid, "group": [1]})
    monkeypatch.setattr(f"{VIEWS}.ModelManage.copy_model", lambda **k: {"model_id": k["new_model_id"]})
    response = ModelViewSet.as_view({"post": "model_copy"})(
        _req("post", superuser, data={"new_model_id": "host2", "new_model_name": "主机2", "copy_attributes": True}),
        model_id="host",
    )
    assert _body(response)["data"]["model_id"] == "host2"


# --------------------------------------------------------------------------
# model_association_type / export / import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_association_type(superuser):
    response = ModelViewSet.as_view({"get": "model_association_type"})(_req("get", superuser))
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(_body(response)["data"], list)


@pytest.mark.django_db
def test_export_model_config(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ModelManage.export_model_config", lambda language=None: io.BytesIO(b"xlsxdata"))
    response = ModelViewSet.as_view({"get": "export_model_config"})(_req("get", superuser))
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
def test_import_model_config_no_file(superuser):
    response = ModelViewSet.as_view({"post": "import_model_config"})(_req("post", superuser, files={}))
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_import_model_config_bad_ext(superuser):
    from django.core.files.uploadedfile import SimpleUploadedFile

    f = SimpleUploadedFile("a.txt", b"x")
    response = ModelViewSet.as_view({"post": "import_model_config"})(_req("post", superuser, files={"file": f}))
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_import_model_config_ok(superuser, monkeypatch):
    from django.core.files.uploadedfile import SimpleUploadedFile

    monkeypatch.setattr(f"{VIEWS}.ModelManage.import_model_config", lambda file: None)
    f = SimpleUploadedFile("a.xlsx", b"x")
    response = ModelViewSet.as_view({"post": "import_model_config"})(_req("post", superuser, files={"file": f}))
    assert response.status_code == status.HTTP_200_OK
