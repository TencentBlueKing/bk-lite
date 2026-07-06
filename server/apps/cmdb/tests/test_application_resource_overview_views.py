import json

import pytest
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


def _req(method, user):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/x/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _post_req(user, data):
    factory = APIRequestFactory()
    request = factory.post("/x/", data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.mark.django_db
def test_topo_themes_returns_app_overview_for_system(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.get_topo_themes", lambda model_id: ["app_overview"])
    response = InstanceViewSet.as_view({"get": "topo_themes"})(
        _req("get", superuser), model_id="system"
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"] == {"themes": ["app_overview"]}


@pytest.mark.django_db
def test_application_resource_apps_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 123, "model_id": "system", "inst_name": "sys-a"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.list_system_applications",
        staticmethod(lambda inst_id, permission_map=None, user=None: [{"id": "11", "name": "app-a", "model_id": "application"}]),
    )
    response = InstanceViewSet.as_view({"get": "application_resource_apps"})(
        _req("get", superuser), model_id="system", inst_id="123"
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["applications"][0]["id"] == "11"


@pytest.mark.django_db
def test_application_resource_topology_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 11, "model_id": "application", "inst_name": "app-a"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_application_topology",
        staticmethod(lambda inst_id, model_id, depth=1, permission_map=None, user=None: {"center": {"id": "11"}, "nodes": [], "links": [], "truncated": False}),
    )
    request = _req("get", superuser)
    request.GET._mutable = True
    request.GET["depth"] = "2"
    response = InstanceViewSet.as_view({"get": "application_resource_topology"})(
        request, model_id="application", inst_id="11"
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["center"]["id"] == "11"


@pytest.mark.django_db
def test_application_resource_resources_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 11, "model_id": "application", "inst_name": "app-a"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_application_resources",
        staticmethod(lambda inst_id, model_id, permission_map=None, user=None: {"groups": {"application": []}, "counts": {"application": 0}}),
    )
    response = InstanceViewSet.as_view({"get": "application_resource_resources"})(
        _req("get", superuser), model_id="application", inst_id="11"
    )
    assert response.status_code == status.HTTP_200_OK
    assert "groups" in _body(response)["data"]


@pytest.mark.django_db
def test_application_resource_instances_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 11, "model_id": "application", "inst_name": "app-a"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_topology_instance_groups",
        staticmethod(lambda node_ids, permission_map=None, user=None: {"groups": [{"model_id": "host", "columns": [], "count": 1, "items": []}], "total": 1}),
    )
    request = _post_req(superuser, {"node_ids": ["11", "21"]})
    response = InstanceViewSet.as_view({"post": "application_resource_instances"})(
        request, model_id="application", inst_id="11"
    )
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["total"] == 1


@pytest.mark.django_db
def test_application_resource_export_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 11, "model_id": "application", "inst_name": "app-a"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.export_topology_instance_groups_excel",
        staticmethod(lambda node_ids, permission_map=None, user=None: b"excel-bytes"),
    )
    request = _post_req(superuser, {"node_ids": ["11", "21"]})
    response = InstanceViewSet.as_view({"post": "application_resource_export"})(
        request, model_id="application", inst_id="11"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
