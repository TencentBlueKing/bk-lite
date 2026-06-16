"""Tests for two new InstanceViewSet actions: topo_themes and network_topo.

Following the pattern established in test_instance_views_extra.py:
- Use InstanceViewSet.as_view({method: action_name})
- Use APIRequestFactory + force_authenticate
- Mock service-layer calls via monkeypatch
"""

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


def _req(method, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    if data is None:
        request = fn("/x/")
    else:
        request = fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


# ---------------------------------------------------------------------------
# topo_themes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_topo_themes_returns_themes(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.get_topo_themes", lambda model_id: ["network"])
    response = InstanceViewSet.as_view({"get": "topo_themes"})(
        _req("get", superuser), model_id="switch"
    )
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"] == {"themes": ["network"]}


@pytest.mark.django_db
def test_topo_themes_empty_for_non_network_model(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.get_topo_themes", lambda model_id: [])
    response = InstanceViewSet.as_view({"get": "topo_themes"})(
        _req("get", superuser), model_id="host"
    )
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"] == {"themes": []}


# ---------------------------------------------------------------------------
# network_topo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_network_topo_ok(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {"_id": 123, "model_id": "switch", "inst_name": "sw"},
    )
    captured = {}

    def _fake_network_topology(inst_id, model_id, depth=1, permission_map=None, user=None):
        captured["depth"] = depth
        return {"center": {"id": "123"}, "nodes": [], "links": [], "truncated": False}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.network_topology", _fake_network_topology)
    response = InstanceViewSet.as_view({"get": "network_topo"})(
        _req("get", superuser), model_id="switch", inst_id="123"
    )
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"]["center"]["id"] == "123"
    assert body["data"]["nodes"] == []
    assert body["data"]["links"] == []
    # 无 depth 查询参数时回退默认 2 跳
    assert captured["depth"] == 2


@pytest.mark.django_db
def test_network_topo_404_when_instance_missing(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: None,
    )
    response = InstanceViewSet.as_view({"get": "network_topo"})(
        _req("get", superuser), model_id="switch", inst_id="999"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_network_topo_404_when_instance_empty_dict(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda pk: {},
    )
    response = InstanceViewSet.as_view({"get": "network_topo"})(
        _req("get", superuser), model_id="switch", inst_id="999"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
