"""CMDB 公共枚举库视图覆盖测试（patch service 模块函数）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：公共枚举库的增删改查、引用查询、错误码映射(404/409/400)。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.public_enum_library import PublicEnumLibraryViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

SVC = "apps.cmdb.views.public_enum_library.library_service"


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    return u


def _req(method, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.mark.django_db
def test_list(superuser, monkeypatch):
    monkeypatch.setattr(f"{SVC}.list_libraries", lambda team: [{"id": 1, "name": "状态枚举"}])
    response = PublicEnumLibraryViewSet.as_view({"get": "list"})(_req("get", superuser))
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"][0]["name"] == "状态枚举"


@pytest.mark.django_db
def test_create_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{SVC}.create_library", lambda payload, operator: {"id": 9})
    response = PublicEnumLibraryViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"name": "x"})
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["id"] == 9


@pytest.mark.django_db
def test_create_error(superuser, monkeypatch):
    def _raise(payload, operator):
        raise BaseAppException("名称重复")

    monkeypatch.setattr(f"{SVC}.create_library", _raise)
    response = PublicEnumLibraryViewSet.as_view({"post": "create"})(
        _req("post", superuser, data={"name": "x"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_update_not_found(superuser, monkeypatch):
    def _raise(pk, payload, operator):
        raise BaseAppException("枚举库不存在")

    monkeypatch.setattr(f"{SVC}.update_library", _raise)
    response = PublicEnumLibraryViewSet.as_view({"put": "update"})(
        _req("put", superuser, data={"name": "x"}), pk="1"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_update_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{SVC}.update_library", lambda pk, payload, operator: {"id": int(pk)})
    response = PublicEnumLibraryViewSet.as_view({"put": "update"})(
        _req("put", superuser, data={"name": "x"}), pk="5"
    )
    assert _body(response)["data"]["id"] == 5


@pytest.mark.django_db
def test_destroy_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{SVC}.delete_library", lambda pk, operator: None)
    response = PublicEnumLibraryViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="5")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_destroy_not_found(superuser, monkeypatch):
    def _raise(pk, operator):
        raise BaseAppException("枚举库不存在")

    monkeypatch.setattr(f"{SVC}.delete_library", _raise)
    response = PublicEnumLibraryViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="5")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_destroy_conflict(superuser, monkeypatch):
    def _raise(pk, operator):
        raise BaseAppException("存在引用", data={"references": [{"model_id": "host"}]})

    monkeypatch.setattr(f"{SVC}.delete_library", _raise)
    response = PublicEnumLibraryViewSet.as_view({"delete": "destroy"})(_req("delete", superuser), pk="5")
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
def test_references_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{SVC}.get_library_or_raise", lambda pk: {"id": int(pk)})
    monkeypatch.setattr(f"{SVC}.find_library_references", lambda pk: [{"model_id": "host"}])
    response = PublicEnumLibraryViewSet.as_view({"get": "references"})(_req("get", superuser), pk="5")
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"][0]["model_id"] == "host"


@pytest.mark.django_db
def test_references_not_found(superuser, monkeypatch):
    def _raise(pk):
        raise BaseAppException("枚举库不存在")

    monkeypatch.setattr(f"{SVC}.get_library_or_raise", _raise)
    response = PublicEnumLibraryViewSet.as_view({"get": "references"})(_req("get", superuser), pk="5")
    assert response.status_code == status.HTTP_404_NOT_FOUND
