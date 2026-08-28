import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet

VIEWS = "apps.cmdb.views.instance"
APP_UUID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
HOST_UUID = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
SYS_UUID = "cccccccc-dddd-4eee-8fff-000000000000"


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


def _entity(inst_uuid: str, *, model_id: str, inst_id: int, inst_name: str):
    return {
        "_id": inst_id,
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": inst_name,
    }


@pytest.mark.django_db
def test_topo_themes_returns_app_overview_for_system(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.get_topo_themes", lambda model_id: ["app_overview"])
    response = InstanceViewSet.as_view({"get": "topo_themes"})(_req("get", superuser), model_id="system")
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"] == {"themes": ["app_overview"]}


@pytest.mark.django_db
def test_application_resource_apps_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="system", inst_id=123, inst_name="sys-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.list_system_applications",
        staticmethod(lambda inst_id, permission_map=None, user=None: [{"id": APP_UUID, "name": "app-a", "model_id": "application"}]),
    )
    response = InstanceViewSet.as_view({"get": "application_resource_apps"})(_req("get", superuser), model_id="system", inst_uuid=SYS_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["applications"][0]["id"] == APP_UUID


@pytest.mark.django_db
def test_application_resource_topology_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_application_topology",
        staticmethod(
            lambda inst_id, model_id, depth=1, permission_map=None, user=None: {
                "center": {"id": APP_UUID},
                "nodes": [],
                "links": [],
                "truncated": False,
            }
        ),
    )
    request = _req("get", superuser)
    request.GET._mutable = True
    request.GET["depth"] = "2"
    response = InstanceViewSet.as_view({"get": "application_resource_topology"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["center"]["id"] == APP_UUID


@pytest.mark.django_db
def test_application_resource_topology_accepts_depth_five(superuser, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_application_topology",
        staticmethod(
            lambda inst_id, model_id, depth=1, permission_map=None, user=None: captured.update(depth=depth)
            or {
                "center": {"id": APP_UUID},
                "nodes": [],
                "links": [],
                "truncated": False,
            }
        ),
    )
    request = _req("get", superuser)
    request.GET._mutable = True
    request.GET["depth"] = "5"
    response = InstanceViewSet.as_view({"get": "application_resource_topology"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert captured["depth"] == 5


@pytest.mark.django_db
def test_application_resource_topology_rejects_depth_six(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    request = _req("get", superuser)
    request.GET._mutable = True
    request.GET["depth"] = "6"
    response = InstanceViewSet.as_view({"get": "application_resource_topology"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_application_resource_resources_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_application_resources",
        staticmethod(
            lambda inst_id, model_id, permission_map=None, user=None: {
                "groups": {"application": []},
                "counts": {"application": 0},
            }
        ),
    )
    response = InstanceViewSet.as_view({"get": "application_resource_resources"})(_req("get", superuser), model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert "groups" in _body(response)["data"]


@pytest.mark.django_db
def test_application_resource_instances_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            _entity(uuids[0], model_id="application", inst_id=11, inst_name="app-a"),
            _entity(uuids[1], model_id="host", inst_id=21, inst_name="host-a"),
        ],
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.build_topology_instance_groups",
        staticmethod(
            lambda node_ids, permission_map=None, user=None: {
                "groups": [{"model_id": "host", "columns": [], "count": 1, "items": []}],
                "total": 1,
            }
        ),
    )
    request = _post_req(superuser, {"node_uuids": [APP_UUID, HOST_UUID]})
    response = InstanceViewSet.as_view({"post": "application_resource_instances"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["data"]["total"] == 1


@pytest.mark.django_db
def test_application_resource_instances_rejects_missing_node_uuids(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    request = _post_req(superuser, {"node_ids": [APP_UUID]})
    response = InstanceViewSet.as_view({"post": "application_resource_instances"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_application_resource_export_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uuid: _entity(uuid, model_id="application", inst_id=11, inst_name="app-a"),
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            _entity(uuids[0], model_id="application", inst_id=11, inst_name="app-a"),
            _entity(uuids[1], model_id="host", inst_id=21, inst_name="host-a"),
        ],
    )
    monkeypatch.setattr(
        f"{VIEWS}.ApplicationResourceOverviewService.export_topology_instance_groups_excel",
        staticmethod(lambda node_ids, permission_map=None, user=None: b"excel-bytes"),
    )
    request = _post_req(superuser, {"node_uuids": [APP_UUID, HOST_UUID]})
    response = InstanceViewSet.as_view({"post": "application_resource_export"})(request, model_id="application", inst_uuid=APP_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
