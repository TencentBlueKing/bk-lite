"""CMDB 配置文件版本视图覆盖测试（patch InstanceManage/ConfigFileService + 真实 DB）。

对照 spec/prd/CMDB·配置文件采集：版本列表/内容/对比/文件清单/手动创建/删除的接口层
参数校验、权限校验与错误码映射。MinIO 内容读取分支不在单测范围（无对象存储）。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.config_file_version import ConfigFileVersion
from apps.cmdb.views.config_file import ConfigFileVersionViewSet

VIEWS = "apps.cmdb.views.config_file"


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    return u


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ConfigFileVersionViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: None,
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": pk, "model_id": "host", "organization": [1], "inst_name": "h"},
    )


@pytest.fixture
def version(db):
    return ConfigFileVersion.objects.create(
        instance_id="5", model_id="host", version="v1",
        file_path="/etc/app.conf", file_name="app.conf", status="success",
    )


def _req(method, user, data=None, query=""):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/" + (f"?{query}" if query else "")
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_missing_params(superuser):
    response = ConfigFileVersionViewSet.as_view({"get": "list"})(_req("get", superuser, query="instance_id=5"))
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_list_instance_not_found(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_id", lambda pk: {})
    response = ConfigFileVersionViewSet.as_view({"get": "list"})(
        _req("get", superuser, query="instance_id=5&file_path=/etc/app.conf")
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_list_ok(superuser, version):
    response = ConfigFileVersionViewSet.as_view({"get": "list"})(
        _req("get", superuser, query="instance_id=5&file_path=/etc/app.conf")
    )
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# content
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_content_not_found(superuser):
    response = ConfigFileVersionViewSet.as_view({"get": "content"})(_req("get", superuser), pk=999999)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_content_no_content(superuser, version):
    # content 字段为空 → 400
    response = ConfigFileVersionViewSet.as_view({"get": "content"})(_req("get", superuser), pk=version.id)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_diff_missing_params(superuser):
    response = ConfigFileVersionViewSet.as_view({"get": "diff"})(_req("get", superuser, query="version_id_1=1"))
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_diff_versions_not_found(superuser):
    response = ConfigFileVersionViewSet.as_view({"get": "diff"})(
        _req("get", superuser, query="version_id_1=88888&version_id_2=99999")
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_diff_no_content(superuser, version):
    v2 = ConfigFileVersion.objects.create(
        instance_id="5", model_id="host", version="v2",
        file_path="/etc/app.conf", file_name="app.conf", status="success",
    )
    response = ConfigFileVersionViewSet.as_view({"get": "diff"})(
        _req("get", superuser, query=f"version_id_1={version.id}&version_id_2={v2.id}")
    )
    # 两个版本均无 content → 仅支持对比成功版本
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# --------------------------------------------------------------------------
# file_list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_file_list_missing(superuser):
    response = ConfigFileVersionViewSet.as_view({"get": "file_list"})(_req("get", superuser))
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_file_list_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.ConfigFileService.get_file_list", lambda iid: [])
    response = ConfigFileVersionViewSet.as_view({"get": "file_list"})(
        _req("get", superuser, query="instance_id=5")
    )
    assert response.status_code == status.HTTP_200_OK


# --------------------------------------------------------------------------
# receive_result
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_receive_result_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ConfigFileService.process_collect_result",
        lambda data: {"version_obj": None, "changed": False, "task_updated": True},
    )
    response = ConfigFileVersionViewSet.as_view({"post": "receive_result"})(
        _req("post", superuser, data={"instance_id": "5"})
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["task_updated"] is True


# --------------------------------------------------------------------------
# create_manual
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_manual_missing_fields(superuser):
    response = ConfigFileVersionViewSet.as_view({"post": "create_manual"})(
        _req("post", superuser, data={"instance_id": "5"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_manual_empty_content(superuser):
    response = ConfigFileVersionViewSet.as_view({"post": "create_manual"})(
        _req("post", superuser, data={"instance_id": "5", "model_id": "host", "file_path": "/a"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_manual_unchanged(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.ConfigFileService.create_manual_version", lambda **k: {"unchanged": True}
    )
    response = ConfigFileVersionViewSet.as_view({"post": "create_manual"})(
        _req("post", superuser, data={"instance_id": "5", "model_id": "host", "file_path": "/a", "content": "x"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_manual_ok(superuser, monkeypatch, version):
    monkeypatch.setattr(
        f"{VIEWS}.ConfigFileService.create_manual_version",
        lambda **k: {"version_obj": version},
    )
    response = ConfigFileVersionViewSet.as_view({"post": "create_manual"})(
        _req("post", superuser, data={"instance_id": "5", "model_id": "host", "file_path": "/a", "content": "x"})
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["version"] == "v1"


# --------------------------------------------------------------------------
# destroy
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_destroy_not_found(superuser):
    response = ConfigFileVersionViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=999999)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_ok(superuser, version):
    response = ConfigFileVersionViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk=version.id)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["deleted_id"] == version.id
