"""CMDB 实例视图覆盖测试（patch InstanceManage + 权限 mixin）。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：实例查询/详情/增删改、批量操作、关联关系的接口层逻辑，
包含纯函数 _normalize_query_list/_parse_positive_int/add_instance_permission。
"""

import importlib
import json
import types

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

VIEWS = "apps.cmdb.views.instance"


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.roles = ["admin"]
    return u


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    # 权限映射统一放行
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission",
        lambda **kwargs: True,
    )
    # mixin 权限方法放行
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_creator_and_organizations", lambda self, r, i: True)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [1])
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_instance_permission", lambda self, r, i, operator=None: True)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.require_instance_permission", lambda self, r, i, operator=None: None)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet._get_allowed_org_ids", staticmethod(lambda request: [1]))


def _req(method, user, data=None, team="1", include_children="0"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _call(action_map, request, **kwargs):
    return InstanceViewSet.as_view(action_map)(request, **kwargs)


# --------------------------------------------------------------------------
# _parse_positive_int（纯函数）
# --------------------------------------------------------------------------


def test_parse_positive_int_default():
    assert InstanceViewSet._parse_positive_int(None, "page", 1) == 1
    assert InstanceViewSet._parse_positive_int("", "page", 5) == 5


def test_parse_positive_int_valid():
    assert InstanceViewSet._parse_positive_int("3", "page", 1) == 3


def test_parse_positive_int_not_int():
    with pytest.raises(ValueError):
        InstanceViewSet._parse_positive_int("abc", "page", 1)


def test_parse_positive_int_too_small():
    with pytest.raises(ValueError):
        InstanceViewSet._parse_positive_int("0", "page", 1)


# --------------------------------------------------------------------------
# _normalize_query_list（纯函数，多分支）
# --------------------------------------------------------------------------


def test_normalize_query_list_none():
    assert InstanceViewSet._normalize_query_list(None) == []


def test_normalize_query_list_dict_to_list():
    out = InstanceViewSet._normalize_query_list({"field": "name", "type": "str=", "value": "h"})
    assert out == [{"field": "name", "type": "str=", "value": "h"}]


def test_normalize_query_list_not_list():
    assert InstanceViewSet._normalize_query_list("bad") == []


def test_normalize_query_list_skips_invalid():
    out = InstanceViewSet._normalize_query_list([{"field": "name"}, {"type": "str="}, {}])
    assert out == []


def test_normalize_query_list_time():
    out = InstanceViewSet._normalize_query_list([{"field": "t", "type": "time", "start": "a", "end": "b"}])
    assert out == [{"field": "t", "type": "time", "start": "a", "end": "b"}]


def test_normalize_query_list_time_missing_bounds():
    out = InstanceViewSet._normalize_query_list([{"field": "t", "type": "time", "start": "a"}])
    assert out == []


def test_normalize_query_list_accurate():
    out = InstanceViewSet._normalize_query_list([{"field": "f", "type": "str=", "value": "v", "accurate": True}])
    assert out[0]["accurate"] is True


def test_normalize_query_list_empty_values_skipped():
    out = InstanceViewSet._normalize_query_list(
        [
            {"field": "f", "type": "str="},  # no value key
            {"field": "f", "type": "str=", "value": None},
            {"field": "f", "type": "str=", "value": ""},
            {"field": "f", "type": "list[]", "value": []},
        ]
    )
    assert out == []


def test_normalize_query_list_nested():
    out = InstanceViewSet._normalize_query_list([[{"field": "f", "type": "str=", "value": "v"}]])
    assert out == [{"field": "f", "type": "str=", "value": "v"}]


# --------------------------------------------------------------------------
# add_instance_permission（纯函数）
# --------------------------------------------------------------------------


def test_add_instance_permission_creator_full():
    instances = [{"_creator": "alice", "inst_name": "h", "organization": [1]}]
    InstanceViewSet.add_instance_permission(instances, {}, creator="alice")
    assert set(instances[0]["permission"]) == {"View", "Operate"}


def test_add_instance_permission_by_org():
    instances = [{"_creator": "bob", "inst_name": "h", "organization": [6]}]
    pmap = {6: {"permission_instances_map": {}}}  # org 6 全选 → View+Operate
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert set(instances[0]["permission"]) == {"View", "Operate"}


def test_add_instance_permission_by_inst_name():
    instances = [{"_creator": "bob", "inst_name": "VC3", "organization": [6]}]
    pmap = {6: {"permission_instances_map": {"VC3": ["View"]}}}
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == ["View"]


def test_add_instance_permission_same_name_other_org_denied():
    instances = [{"_creator": "bob", "inst_name": "prod-vc", "organization": [9]}]
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == []


def test_add_instance_permission_same_name_same_org_allowed():
    instances = [{"_creator": "bob", "inst_name": "prod-vc", "organization": [6]}]
    pmap = {6: {"permission_instances_map": {"prod-vc": ["View"]}}}
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == ["View"]


def test_add_instance_permission_same_name_ignores_other_org_permissions():
    instances = [{"_creator": "bob", "inst_name": "prod-vc", "organization": [6]}]
    pmap = {
        6: {"permission_instances_map": {"prod-vc": ["View"]}},
        8: {"permission_instances_map": {"prod-vc": ["Operate"]}},
    }
    InstanceViewSet.add_instance_permission(instances, pmap, creator="alice")
    assert instances[0]["permission"] == ["View"]


# --------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_missing_model_id(superuser):
    request = _req("post", superuser, data={})
    response = _call({"post": "search"}, request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_search_bad_page(superuser):
    request = _req("post", superuser, data={"model_id": "host", "page": "abc"})
    response = _call({"post": "search"}, request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_search_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_list",
        lambda **kwargs: ([{"_creator": "admin", "inst_name": "h", "organization": [1]}], 1),
    )
    request = _req("post", superuser, data={"model_id": "host"})
    response = _call({"post": "search"}, request)
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["count"] == 1


# --------------------------------------------------------------------------
# retrieve
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_retrieve_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    request = _req("get", superuser)
    response = _call({"get": "retrieve"}, request, pk="5")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_retrieve_creator(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "host", "inst_name": "h", "organization": [1]},
    )
    request = _req("get", superuser)
    response = _call({"get": "retrieve"}, request, pk="5")
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert set(body["data"]["permission"]) == {"View", "Operate"}


@pytest.mark.django_db
def test_retrieve_denied_when_name_permission_only_exists_in_other_org(superuser, monkeypatch):
    permission_module = importlib.reload(importlib.import_module("apps.cmdb.utils.permission_util"))

    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "vmware_vc", "inst_name": "prod-vc", "organization": [9], "_creator": "alice"},
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_creator_and_organizations", lambda self, r, i: False)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [9])
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission",
        permission_module.CmdbRulesFormatUtil.has_object_permission,
    )
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {
            6: {"permission_instances_map": {"prod-vc": ["View"]}, "inst_names": ["prod-vc"]}
        },
    )
    request = _req("get", superuser, team="9")
    response = _call({"get": "retrieve"}, request, pk="5")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_ok(superuser, monkeypatch):
    calls = []

    def _create(model_id, info, username, **kwargs):
        calls.append(kwargs)
        return {"_id": 9, "model_id": model_id, "inst_name": info["inst_name"]}

    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_create",
        _create,
    )
    request = _req("post", superuser, data={"model_id": "host", "instance_info": {"inst_name": "h"}})
    request.META["HTTP_IDEMPOTENCY_KEY"] = "create-host-1"
    response = _call({"post": "create"}, request)
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["_id"] == 9
    assert calls[0]["record_change"] is False
    assert calls[0]["schedule_post_actions"] is False
    assert calls[0]["operation_id"]


@pytest.mark.django_db
def test_create_same_idempotency_key_returns_original_result_without_graph_replay(superuser, monkeypatch):
    calls = []

    def _create(model_id, info, username, **kwargs):
        calls.append(info)
        return {"_id": 9, "model_id": model_id, "inst_name": info["inst_name"]}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.instance_create", _create)

    responses = []
    for _ in range(2):
        request = _req("post", superuser, data={"model_id": "host", "instance_info": {"inst_name": "h"}})
        request.META["HTTP_IDEMPOTENCY_KEY"] = "create-host-1"
        responses.append(_call({"post": "create"}, request))

    assert [_body(response)["data"]["_id"] for response in responses] == [9, 9]
    assert len(calls) == 1


# --------------------------------------------------------------------------
# destroy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_destroy_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    request = _req("delete", superuser)
    response = _call({"delete": "destroy"}, request, pk=5)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "host", "inst_name": "h", "organization": [1]},
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.instance_batch_delete", lambda *a, **k: None)
    request = _req("delete", superuser)
    response = _call({"delete": "destroy"}, request, pk=5)
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# instance_batch_delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_delete_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_ids", lambda data: [])
    request = _req("post", superuser, data=[1, 2])
    response = _call({"post": "instance_batch_delete"}, request)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_batch_delete_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_ids",
        lambda data: [{"_id": 1, "model_id": "host", "inst_name": "h", "organization": [1]}],
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.instance_batch_delete", lambda *a, **k: None)
    request = _req("post", superuser, data=[1])
    response = _call({"post": "instance_batch_delete"}, request)
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# partial_update
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_partial_update_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    request = _req("patch", superuser, data={"inst_name": "h2"})
    response = _call({"patch": "partial_update"}, request, pk=5)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_partial_update_ok(superuser, monkeypatch):
    calls = []
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "host", "inst_name": "h", "organization": [1]},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_update",
        lambda *a, **k: calls.append(k) or {"_id": 5, "model_id": "host", "inst_name": "h2"},
    )
    request = _req("patch", superuser, data={"inst_name": "h2"})
    request.META["HTTP_IDEMPOTENCY_KEY"] = "update-host-5"
    response = _call({"patch": "partial_update"}, request, pk=5)
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["inst_name"] == "h2"
    assert calls[0]["record_change"] is False
    assert calls[0]["schedule_post_actions"] is False
    assert calls[0]["operation_id"]


@pytest.mark.django_db
def test_partial_update_same_idempotency_key_does_not_replay_graph_write(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 5, "model_id": "host", "inst_name": "h", "organization": [1]},
    )
    calls = []
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_update",
        lambda *a, **k: calls.append(k) or {"_id": 5, "model_id": "host", "inst_name": "h2"},
    )

    for _ in range(2):
        request = _req("patch", superuser, data={"inst_name": "h2"})
        request.META["HTTP_IDEMPOTENCY_KEY"] = "update-host-5"
        response = _call({"patch": "partial_update"}, request, pk=5)
        assert _body(response)["data"]["inst_name"] == "h2"

    assert len(calls) == 1


# --------------------------------------------------------------------------
# instance_batch_update（参数校验）
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_update_bad_inst_ids(superuser):
    request = _req("post", superuser, data={"inst_ids": [], "update_data": {"a": 1}})
    response = _call({"post": "instance_batch_update"}, request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_batch_update_bad_update_data(superuser):
    request = _req("post", superuser, data={"inst_ids": [1], "update_data": {}})
    response = _call({"post": "instance_batch_update"}, request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_batch_update_empty_instances(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_ids", lambda ids: [])
    request = _req("post", superuser, data={"inst_ids": [1], "update_data": {"a": 1}})
    response = _call({"post": "instance_batch_update"}, request)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_batch_update_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_ids",
        lambda ids: [{"_id": 1, "model_id": "host", "inst_name": "h", "organization": [1]}],
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.batch_instance_update", lambda *a, **k: None)
    request = _req("post", superuser, data={"inst_ids": [1], "update_data": {"a": 1}})
    response = _call({"post": "instance_batch_update"}, request)
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# instance_association_create / delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_association_create_src_missing(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {} if pk == 1 else {"_id": pk})
    request = _req("post", superuser, data={"src_inst_id": 1, "dst_inst_id": 2})
    response = _call({"post": "instance_association_create"}, request)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_association_create_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": pk, "inst_name": f"i{pk}", "organization": [1]},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_association_create",
        lambda data, username: {"_id": 100},
    )
    request = _req("post", superuser, data={"src_inst_id": 1, "dst_inst_id": 2, "asst_id": "a"})
    response = _call({"post": "instance_association_create"}, request)
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"]["_id"] == 100


@pytest.mark.django_db
def test_association_delete_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.instance_association_by_asso_id", lambda aid: None)
    request = _req("delete", superuser)
    response = _call({"delete": "instance_association_delete"}, request, id="3")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_association_delete_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_association_by_asso_id",
        lambda aid: {
            "src": {"_id": 1, "inst_name": "s", "organization": [1]},
            "dst": {"_id": 2, "inst_name": "d", "organization": [1]},
        },
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.instance_association_delete", lambda aid, username: None)
    request = _req("delete", superuser)
    response = _call({"delete": "instance_association_delete"}, request, id="3")
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# instance_association_instance_list / instance_association
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_association_instance_list_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    request = _req("get", superuser)
    response = _call({"get": "instance_association_instance_list"}, request, model_id="host", inst_id="5")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_association_instance_list_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {"_id": 5, "organization": [1]})
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_association_instance_list",
        lambda model_id, inst_id: [{"_id": 9}],
    )
    request = _req("get", superuser)
    response = _call({"get": "instance_association_instance_list"}, request, model_id="host", inst_id="5")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_instance_association_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {"_id": 5, "organization": [1]})
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.instance_association",
        lambda model_id, inst_id: [{"_id": 9}],
    )
    request = _req("get", superuser)
    response = _call({"get": "instance_association"}, request, model_id="host", inst_id="5")
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# 附件/图片文件接口（upload_file / download_file / delete_file）— 视图接线
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_download_file_returns_presigned_url_after_permission(superuser, monkeypatch):
    captured = {}

    def handle_download(*, request, file_id, check_read_permission=None, as_attachment=False):
        captured["file_id"] = file_id
        captured["has_cb"] = callable(check_read_permission)
        captured["as_attachment"] = as_attachment
        return "https://minio/presigned-url"

    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: types.SimpleNamespace(handle_download=handle_download),
    )
    response = _call({"get": "download_file"}, _req("get", superuser), file_id="fid-1")
    body = _body(response)
    # 返回 JSON 预签名直链（前端经 axios 带令牌取，再直接用于 img/下载）
    assert body["result"] is True
    assert body["data"]["url"] == "https://minio/presigned-url"
    assert captured["file_id"] == "fid-1"
    # 下载校权回调被透传给企业实现（实例读权限）
    assert captured["has_cb"] is True
    # 默认内联（预览用），未要求附件下载
    assert captured["as_attachment"] is False


@pytest.mark.django_db
def test_download_file_attachment_disposition_when_download_flag(superuser, monkeypatch):
    """download=1 时透传 as_attachment=True，使企业实现生成附件 disposition 的预签名 URL。"""
    captured = {}

    def handle_download(*, request, file_id, check_read_permission=None, as_attachment=False):
        captured["as_attachment"] = as_attachment
        return "https://minio/presigned-url"

    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: types.SimpleNamespace(handle_download=handle_download),
    )
    factory = APIRequestFactory()
    request = factory.get("/x/", data={"download": "1"})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=superuser)
    response = _call({"get": "download_file"}, request, file_id="fid-1")
    assert _body(response)["result"] is True
    assert captured["as_attachment"] is True


@pytest.mark.django_db
def test_upload_file_requires_model_and_attr(superuser):
    response = _call({"post": "upload_file"}, _req("post", superuser, data={}))
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_upload_file_delegates_to_extension(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: types.SimpleNamespace(
            handle_upload=lambda *, request, model_id, attr_id, uploaded_file: {
                "file_id": "x",
                "file_name": uploaded_file.name,
            }
        ),
    )
    factory = APIRequestFactory()
    upload = SimpleUploadedFile("a.pdf", b"data", content_type="application/pdf")
    request = factory.post(
        "/x/", data={"model_id": "host", "attr_id": "contract", "file": upload}, format="multipart"
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=superuser)
    response = _call({"post": "upload_file"}, request)
    body = _body(response)
    assert body["result"] is True
    assert body["data"]["file_id"] == "x"
    assert body["data"]["file_name"] == "a.pdf"


@pytest.mark.django_db
def test_delete_file_delegates_to_extension(superuser, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        f"{VIEWS}.get_instance_enterprise_extension",
        lambda: types.SimpleNamespace(
            handle_delete_temp=lambda *, request, file_id: captured.update(file_id=file_id)
        ),
    )
    response = _call({"delete": "delete_file"}, _req("delete", superuser), file_id="fid-9")
    body = _body(response)
    assert body["result"] is True
    assert captured["file_id"] == "fid-9"
