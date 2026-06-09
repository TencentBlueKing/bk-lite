"""CMDB 杂项视图覆盖测试：分类/展示字段/变更记录/用户个人配置 + 权限 Mixin。

对照 spec/prd/CMDB·模型管理与操作日志：分类增删改查、实例展示字段设置、
变更记录枚举与列表、用户个人配置 CRUD，以及 CmdbPermissionMixin 的对象级权限判定。
"""

import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.classification import ClassificationViewSet
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.cmdb.views.show_field import ShowFieldViewSet
from apps.cmdb.views.user_personal_config import UserPersonalConfigViewSet


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.roles = ["admin"]
    u.locale = "zh-Hans"
    u.domain = "domain.com"
    return u


def _req(method, user, data=None, **cookies):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    for k, v in cookies.items():
        request.COOKIES[k] = v
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# ==========================================================================
# CmdbPermissionMixin（纯逻辑）
# ==========================================================================


def _mixin_request(group_list, username="admin", include_children="0", current_team="1", group_tree=None):
    user = SimpleNamespace(
        group_list=group_list, username=username, group_tree=group_tree or []
    )
    return SimpleNamespace(user=user, COOKIES={"include_children": include_children, "current_team": current_team})


def test_get_user_organizations_intersection():
    req = _mixin_request([{"id": 1}, {"id": 2}])
    out = CmdbPermissionMixin.get_user_organizations(req, {"organization": [2, 3]})
    assert out == [2]


def test_is_creator_with_org_access_true():
    req = _mixin_request([{"id": 1}], username="alice", current_team="1")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is True


def test_is_creator_with_org_access_wrong_team():
    req = _mixin_request([{"id": 9}], username="alice", current_team="9")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is False


def test_is_creator_with_org_access_not_creator():
    req = _mixin_request([{"id": 1}], username="bob", current_team="1")
    instance = {"organization": [1], "_creator": "alice"}
    assert CmdbPermissionMixin.is_creator_with_org_access(req, instance) is False


def test_check_instance_permission_no_org():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}], current_team="9")
    assert mixin.check_instance_permission(req, {"organization": [1], "model_id": "host"}) is False


def test_check_instance_permission_granted(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **k: {1: {"permission_instances_map": {}}},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: True
    )
    req = _mixin_request([{"id": 1}])
    assert mixin.check_instance_permission(req, {"organization": [1], "model_id": "host"}) is True


def test_check_model_permission_no_org():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}])
    assert mixin.check_model_permission(req, {"group": [1], "model_id": "host"}) is False


def test_require_instance_permission_creator_ok():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 1}], username="alice", current_team="1")
    instance = {"organization": [1], "_creator": "alice", "model_id": "host"}
    assert mixin.require_instance_permission(req, instance) is None


def test_require_instance_permission_no_org_denied():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}], username="bob", current_team="9")
    instance = {"organization": [1], "_creator": "alice", "model_id": "host"}
    resp = mixin.require_instance_permission(req, instance)
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


def test_require_model_permission_no_org_denied():
    mixin = CmdbPermissionMixin()
    req = _mixin_request([{"id": 9}])
    resp = mixin.require_model_permission(req, {"group": [1], "model_id": "host"})
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


def test_require_model_view_permission_default_group(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: True
    )
    req = _mixin_request([{"id": 9}])
    # default_group 模型即使无组织交集也可继续 VIEW 判定
    resp = mixin.require_model_view_permission(
        req, {"group": [1], "model_id": "host"}, default_group_id=1, permissions_map={1: {}}
    )
    assert resp is None


def test_require_model_view_permission_denied(monkeypatch):
    mixin = CmdbPermissionMixin()
    monkeypatch.setattr(
        "apps.cmdb.views.mixins.CmdbRulesFormatUtil.has_object_permission", lambda **k: False
    )
    req = _mixin_request([{"id": 1}])
    resp = mixin.require_model_view_permission(
        req, {"group": [1], "model_id": "host"}, default_group_id=1, permissions_map={1: {}}
    )
    assert resp is not None and resp.status_code == status.HTTP_403_FORBIDDEN


# ==========================================================================
# ClassificationViewSet
# ==========================================================================


@pytest.mark.django_db
def test_classification_create(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.create_model_classification",
        lambda data: {"classification_id": data.get("classification_id", "net")},
    )
    request = _req("post", superuser, data={"classification_id": "net", "classification_name": "网络"})
    response = ClassificationViewSet.as_view({"post": "create"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["classification_id"] == "net"


@pytest.mark.django_db
def test_classification_list(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification",
        lambda locale, **kwargs: [{"classification_id": "net"}],
    )
    request = _req("get", superuser)
    response = ClassificationViewSet.as_view({"get": "list"})(request)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"][0]["classification_id"] == "net"


@pytest.mark.django_db
def test_classification_destroy(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.check_classification_is_used", lambda pk: None
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification_info",
        lambda pk: {"_id": 12},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.delete_model_classification", lambda _id: None
    )
    request = _req("delete", superuser)
    response = ClassificationViewSet.as_view({"delete": "destroy"})(request, pk="net")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_classification_update(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.search_model_classification_info",
        lambda pk: {"_id": 12},
    )
    monkeypatch.setattr(
        "apps.cmdb.views.classification.ClassificationManage.update_model_classification",
        lambda _id, data: {"_id": _id, **data},
    )
    request = _req("put", superuser, data={"classification_name": "网络2"})
    response = ClassificationViewSet.as_view({"put": "update"})(request, pk="net")
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["classification_name"] == "网络2"


# ==========================================================================
# ShowFieldViewSet（真实 DB）
# ==========================================================================


@pytest.mark.django_db
def test_show_field_invalid_payload(superuser):
    request = _req("post", superuser, data={"show_fields": "notalist"})
    response = ShowFieldViewSet.as_view({"post": "create_or_update"})(request, model_id="host")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_show_field_create_then_get(superuser):
    request = _req("post", superuser, data={"show_fields": ["inst_name", "ip"]})
    response = ShowFieldViewSet.as_view({"post": "create_or_update"})(request, model_id="host")
    assert response.status_code == status.HTTP_200_OK

    get_req = _req("get", superuser)
    get_resp = ShowFieldViewSet.as_view({"get": "get_info"})(get_req, model_id="host")
    body = _body(get_resp)
    assert body["data"]["show_fields"] == ["inst_name", "ip"]


@pytest.mark.django_db
def test_show_field_get_none(superuser):
    request = _req("get", superuser)
    response = ShowFieldViewSet.as_view({"get": "get_info"})(request, model_id="absent")
    assert _body(response)["data"] is None


# ==========================================================================
# UserPersonalConfigViewSet（真实 DB）
# ==========================================================================


@pytest.mark.django_db
def test_user_config_create_bad_value(superuser):
    request = _req("post", superuser, data={"config_key": "k", "config_value": "notdict"})
    response = UserPersonalConfigViewSet.as_view({"post": "create"})(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_config_crud_flow(superuser):
    # create —— 视图自带 {"result","data"} 信封，外层 renderer 再包一层 data
    create_resp = UserPersonalConfigViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"config_key": "dashboard", "config_value": {"a": 1}})
    )
    assert create_resp.status_code == status.HTTP_200_OK
    cfg_id = _body(create_resp)["data"]["data"]["id"]

    # list
    list_resp = UserPersonalConfigViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert _body(list_resp)["data"]["result"] is True

    # retrieve
    ret_resp = UserPersonalConfigViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=cfg_id)
    assert _body(ret_resp)["data"]["data"]["config_key"] == "dashboard"

    # destroy
    del_resp = UserPersonalConfigViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=cfg_id)
    assert _body(del_resp)["data"]["result"] is True


@pytest.mark.django_db
def test_user_config_get_by_key_missing(superuser):
    response = UserPersonalConfigViewSet.as_view({"get": "get_by_key"})(
        _req("get", superuser), config_key="absent"
    )
    assert _body(response)["data"]["data"] == {}


@pytest.mark.django_db
def test_user_config_update_key(superuser):
    response = UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "layout", "config_value": {"x": 1}})
    )
    body = _body(response)
    assert body["result"] is True
    assert body["data"]["data"]["config_key"] == "layout"


@pytest.mark.django_db
def test_user_config_update_key_bad(superuser):
    response = UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "", "config_value": {"x": 1}})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_user_config_delete_key_and_list_keys(superuser):
    # 先建一个 key
    UserPersonalConfigViewSet.as_view({"post": "update_key"})(
        _req("post", superuser, data={"config_key": "to_del", "config_value": {"x": 1}})
    )
    # list_keys
    keys_resp = UserPersonalConfigViewSet.as_view({"get": "list_keys"})(_req("get", superuser))
    assert "to_del" in _body(keys_resp)["data"]["data"]
    # delete_key 返回裸 bool
    del_resp = UserPersonalConfigViewSet.as_view({"delete": "delete_key"})(
        _req("delete", superuser), config_key="to_del"
    )
    assert _body(del_resp)["data"] is True
