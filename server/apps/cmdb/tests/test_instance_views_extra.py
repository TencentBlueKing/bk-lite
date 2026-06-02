"""CMDB 实例视图剩余分支覆盖：拓扑、全文检索、导入/导出、show_field、模型实例计数、代理列表。

对照 spec/prd/CMDB·资产：拓扑查询、全文检索（含校验）、Excel 导入导出、展示字段配置、
按模型实例计数、云区域代理列表（节点管理）。
"""

import io
import json

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet

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
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: None,
    )
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", lambda **k: True
    )


def _req(method, user, data=None, query="", files=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/" + (f"?{query}" if query else "")
    if files is not None:
        request = fn(path, data=files, format="multipart")
    elif data is None:
        request = fn(path)
    else:
        request = fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# topo_search / topo_search_expand_post / topo_search_test_config
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_topo_search_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    response = InstanceViewSet.as_view({"get": "topo_search"})(
        _req("get", superuser), model_id="host", inst_id="5"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_topo_search_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id",
                        lambda pk: {"_id": 5, "model_id": "host"})
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.topo_search_lite",
                        lambda *a, **k: {"src_result": {"_id": 5}})
    response = InstanceViewSet.as_view({"get": "topo_search"})(
        _req("get", superuser), model_id="host", inst_id="5"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_topo_search_expand_post_missing_inst_id(superuser):
    response = InstanceViewSet.as_view({"post": "topo_search_expand_post"})(
        _req("post", superuser, data={"parent_id": []})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_topo_search_expand_post_bad_inst_id(superuser):
    response = InstanceViewSet.as_view({"post": "topo_search_expand_post"})(
        _req("post", superuser, data={"inst_id": "abc"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_topo_search_expand_post_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    response = InstanceViewSet.as_view({"post": "topo_search_expand_post"})(
        _req("post", superuser, data={"inst_id": 5, "parent_id": 1})
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_topo_search_expand_post_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id",
                        lambda pk: {"_id": 5, "model_id": "host"})
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.topo_search_expand",
                        lambda *a, **k: {"src_result": {"_id": 5}})
    response = InstanceViewSet.as_view({"post": "topo_search_expand_post"})(
        _req("post", superuser, data={"inst_id": 5, "parent_id": [1]})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_topo_search_test_config_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id",
                        lambda pk: {"_id": 5, "model_id": "host"})
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.topo_search_test_config",
                        lambda iid, mid: {"ok": True})
    response = InstanceViewSet.as_view({"get": "topo_search_test_config"})(
        _req("get", superuser), model_id="host", inst_id="5"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_topo_search_test_config_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    response = InstanceViewSet.as_view({"get": "topo_search_test_config"})(
        _req("get", superuser), model_id="host", inst_id="5"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# --------------------------------------------------------------------------
# fulltext_search / stats / by_model
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_fulltext_search_view(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.fulltext_search",
                        lambda **k: [{"_id": 1, "inst_name": "h"}])
    response = InstanceViewSet.as_view({"post": "fulltext_search"})(
        _req("post", superuser, data={"search": "h"})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_fulltext_search_stats_view_no_keyword(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_stats"})(
        _req("post", superuser, data={})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_stats_view_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.fulltext_search_stats",
                        lambda **k: {"total": 1, "model_stats": []})
    response = InstanceViewSet.as_view({"post": "fulltext_search_stats"})(
        _req("post", superuser, data={"search": "h"})
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_fulltext_search_by_model_no_search(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"model_id": "host"})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_by_model_no_model_id(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"search": "h"})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_by_model_bad_page(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"search": "h", "model_id": "host", "page": "abc"})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_by_model_page_too_small(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"search": "h", "model_id": "host", "page": 0})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_by_model_page_size_too_big(superuser):
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"search": "h", "model_id": "host", "page_size": 200})
    )
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_fulltext_search_by_model_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.fulltext_search_by_model",
        lambda **k: {"total": 1, "data": []},
    )
    response = InstanceViewSet.as_view({"post": "fulltext_search_by_model"})(
        _req("post", superuser, data={"search": "h", "model_id": "host"})
    )
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# inst_export
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_export_view(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.inst_export",
                        lambda **k: io.BytesIO(b"xlsxdata"))
    response = InstanceViewSet.as_view({"post": "inst_export"})(
        _req("post", superuser, data={"inst_ids": []}), model_id="host"
    )
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")


# --------------------------------------------------------------------------
# download_template
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_download_template_view(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.download_import_template",
                        lambda mid: io.BytesIO(b"xlsxdata"))
    response = InstanceViewSet.as_view({"get": "download_template"})(
        _req("get", superuser), model_id="host"
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# inst_import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_import_no_team(superuser, monkeypatch):
    request = _req("post", superuser, files={}, team="")
    request.COOKIES.pop("current_team", None)
    response = InstanceViewSet.as_view({"post": "inst_import"})(request, model_id="host")
    body = _body(response)
    assert body["result"] is False


@pytest.mark.django_db
def test_inst_import_bad_team(superuser):
    request = _req("post", superuser, files={}, team="abc")
    response = InstanceViewSet.as_view({"post": "inst_import"})(request, model_id="host")
    body = _body(response)
    assert body["result"] is False


@pytest.mark.django_db
def test_inst_import_no_file(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.system_mgmt.utils.group_utils.GroupUtils.get_all_child_groups",
        lambda t, include_self=True, group_list=None: [int(t)],
    )
    response = InstanceViewSet.as_view({"post": "inst_import"})(
        _req("post", superuser, files={}, team="1"), model_id="host"
    )
    body = _body(response)
    assert body["result"] is False


@pytest.mark.django_db
def test_inst_import_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.system_mgmt.utils.group_utils.GroupUtils.get_all_child_groups",
        lambda t, include_self=True, group_list=None: [int(t)],
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.inst_import_support_edit",
        lambda self, model_id, file_stream, operator, allowed_org_ids=None: {"success": True, "message": "OK"},
    )
    f = SimpleUploadedFile("a.xlsx", b"data")
    response = InstanceViewSet.as_view({"post": "inst_import"})(
        _req("post", superuser, files={"file": f}, team="1"), model_id="host"
    )
    body = _body(response)
    assert body["result"] is True


# --------------------------------------------------------------------------
# show_field / model_inst_count / list_proxys
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_show_field_create_or_update(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.create_or_update",
                        lambda data: {"model_id": data["model_id"]})
    response = InstanceViewSet.as_view({"post": "create_or_update"})(
        _req("post", superuser, data=["a", "b"]), model_id="host"
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_show_field_get_info(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.get_info",
                        lambda mid, uname: {"model_id": mid, "show_fields": []})
    response = InstanceViewSet.as_view({"get": "get_info"})(_req("get", superuser), model_id="host")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_model_inst_count(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.model_inst_count",
                        lambda **k: [{"model_id": "host", "count": 3}])
    response = InstanceViewSet.as_view({"get": "model_inst_count"})(_req("get", superuser))
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_list_proxys(superuser, monkeypatch):
    class _FakeNodeMgmt:
        def cloud_region_list(self):
            return [{"id": 1, "name": "default"}, {"id": None, "name": "x"}, "bad"]

    monkeypatch.setattr(f"{VIEWS}.NodeMgmt", _FakeNodeMgmt)
    response = InstanceViewSet.as_view({"get": "list_proxys"})(_req("get", superuser))
    body = _body(response)
    assert response.status_code == status.HTTP_200_OK
    assert body["data"] == [{"proxy_id": 1, "proxy_name": "default"}]
