"""NameSpace / DataSource CRUD：ids 过滤、审计、组织删除闸与 brief 列表。"""
import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.views import datasource_view
from apps.system_mgmt.models import OperationLog

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


def _superuser(user):
    user.is_superuser = True
    return user


def _req(method, path, user, data=None, query=""):
    fn = getattr(factory, method)
    url = f"{path}{query}"
    request = fn(url, data=data or {}, format="json") if data is not None else fn(url)
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _render(resp):
    resp.render()
    if not resp.content:
        return None
    return json.loads(resp.content.decode("utf-8"))


def test_namespace_list_filters_ids_and_crud_writes_audit(authenticated_user):
    user = _superuser(authenticated_user)
    ns1 = NameSpace.objects.create(name="ns-keep", account="a", password="p1", domain="127.0.0.1:4222")
    ns2 = NameSpace.objects.create(name="ns-drop", account="a", password="p2", domain="127.0.0.1:4222")

    listed = datasource_view.NameSpaceModelViewSet.as_view({"get": "list"})(_req("get", "/namespace/", user, query=f"?ids={ns1.id},"))
    payload = _render(listed)
    assert listed.status_code == status.HTTP_200_OK
    items = payload["data"]["items"] if isinstance(payload.get("data"), dict) else payload.get("data") or payload
    names = {item["name"] for item in items}
    assert "ns-keep" in names
    assert "ns-drop" not in names

    created = datasource_view.NameSpaceModelViewSet.as_view({"post": "create"})(
        _req(
            "post",
            "/namespace/",
            user,
            data={"name": "ns-new", "account": "acct", "password": "secret", "domain": "nats.local:4222"},
        )
    )
    payload = _render(created)
    assert created.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "ns-new"
    ns = NameSpace.objects.get(name="ns-new")
    log = OperationLog.objects.get(app="ops-analysis", action_type="create", summary="新增命名空间: ns-new")
    assert log.username == "testuser"

    updated = datasource_view.NameSpaceModelViewSet.as_view({"put": "update"})(
        _req(
            "put",
            f"/namespace/{ns.id}/",
            user,
            data={"name": "ns-renamed", "account": "acct", "password": "secret", "domain": "nats.local:4222"},
        ),
        pk=str(ns.id),
    )
    payload = _render(updated)
    assert updated.status_code == status.HTTP_200_OK
    ns.refresh_from_db()
    assert ns.name == "ns-renamed"
    assert OperationLog.objects.filter(summary="编辑命名空间: ns-renamed").exists()

    retrieved = datasource_view.NameSpaceModelViewSet.as_view({"get": "retrieve"})(
        _req("get", f"/namespace/{ns.id}/", user),
        pk=str(ns.id),
    )
    payload = _render(retrieved)
    assert retrieved.status_code == status.HTTP_200_OK
    assert payload["data"]["name"] == "ns-renamed"

    deleted = datasource_view.NameSpaceModelViewSet.as_view({"delete": "destroy"})(
        _req("delete", f"/namespace/{ns.id}/", user),
        pk=str(ns.id),
    )
    _render(deleted)
    assert not NameSpace.objects.filter(id=ns.id).exists()
    assert OperationLog.objects.filter(summary="删除命名空间: ns-renamed").exists()
    assert NameSpace.objects.filter(id=ns2.id).exists()


def test_datasource_create_update_destroy_and_foreign_team_forbidden(authenticated_user, monkeypatch):
    user = _superuser(authenticated_user)
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )

    created = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "create"})(
        _req(
            "post",
            "/data_source/",
            user,
            data={"name": "ds-a", "groups": [1], "rest_api": "monitor/query", "source_type": "nats"},
        )
    )
    payload = _render(created)
    assert created.status_code == status.HTTP_201_CREATED
    assert payload["data"]["name"] == "ds-a"
    ds = DataSourceAPIModel.objects.get(name="ds-a")
    assert OperationLog.objects.filter(summary="新增数据源: ds-a").exists()

    updated = datasource_view.DataSourceAPIModelViewSet.as_view({"put": "update"})(
        _req(
            "put",
            f"/data_source/{ds.id}/",
            user,
            data={"name": "ds-b", "groups": [1], "rest_api": "monitor/query", "source_type": "nats"},
        ),
        pk=str(ds.id),
    )
    payload = _render(updated)
    assert updated.status_code == status.HTTP_200_OK
    ds.refresh_from_db()
    assert ds.name == "ds-b"
    assert OperationLog.objects.filter(summary="编辑数据源: ds-b").exists()

    listed = datasource_view.DataSourceAPIModelViewSet.as_view({"get": "list"})(_req("get", "/data_source/", user, query=f"?ids={ds.id}&mode=brief"))
    payload = _render(listed)
    assert listed.status_code == status.HTTP_200_OK

    retrieved = datasource_view.DataSourceAPIModelViewSet.as_view({"get": "retrieve"})(
        _req("get", f"/data_source/{ds.id}/", user),
        pk=str(ds.id),
    )
    payload = _render(retrieved)
    assert retrieved.status_code == status.HTTP_200_OK
    assert payload["data"]["name"] == "ds-b"

    foreign = DataSourceAPIModel.objects.create(name="ds-other", groups=[9], rest_api="x/y")
    forbidden = datasource_view.DataSourceAPIModelViewSet.as_view({"delete": "destroy"})(
        _req("delete", f"/data_source/{foreign.id}/", user),
        pk=str(foreign.id),
    )
    payload = _render(forbidden)
    assert forbidden.status_code == status.HTTP_403_FORBIDDEN
    assert "无权删除该数据源" in json.dumps(payload, ensure_ascii=False)
    assert DataSourceAPIModel.objects.filter(id=foreign.id).exists()

    deleted = datasource_view.DataSourceAPIModelViewSet.as_view({"delete": "destroy"})(
        _req("delete", f"/data_source/{ds.id}/", user),
        pk=str(ds.id),
    )
    _render(deleted)
    assert not DataSourceAPIModel.objects.filter(id=ds.id).exists()
    assert OperationLog.objects.filter(summary="删除数据源: ds-b").exists()
