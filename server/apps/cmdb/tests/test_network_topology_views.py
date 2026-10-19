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

from apps.cmdb.constants.constants import NETWORK_TOPO_NODE_LIMIT
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
    response = InstanceViewSet.as_view({"get": "topo_themes"})(_req("get", superuser), model_id="switch")
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"] == {"themes": ["network"]}


@pytest.mark.django_db
def test_topo_themes_empty_for_non_network_model(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.get_topo_themes", lambda model_id: [])
    response = InstanceViewSet.as_view({"get": "topo_themes"})(_req("get", superuser), model_id="host")
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"] == {"themes": []}


# ---------------------------------------------------------------------------
# network_topo
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_network_topo_ok(superuser, monkeypatch):
    sample_uuid = "550e8400-e29b-41d4-a716-446655440000"
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uid: {"_id": 123, "model_id": "switch", "inst_name": "sw", "inst_uuid": uid},
    )
    captured = {}

    def _fake_network_topology_by_uuid(inst_uuid, model_id, depth=1, permission_map=None, user=None, node_limit=None):
        captured["depth"] = depth
        captured["inst_uuid"] = inst_uuid
        return {"center": {"id": inst_uuid}, "nodes": [], "links": [], "truncated": False}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.network_topology_by_uuid", _fake_network_topology_by_uuid)
    response = InstanceViewSet.as_view({"get": "network_topo"})(_req("get", superuser), model_id="switch", inst_uuid=sample_uuid)
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["data"]["center"]["id"] == sample_uuid
    assert body["data"]["nodes"] == []
    assert body["data"]["links"] == []
    # 无 depth 查询参数时回退默认 2 跳
    assert captured["depth"] == 2
    assert captured["inst_uuid"] == sample_uuid


@pytest.mark.django_db
def test_network_topo_404_when_instance_missing(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uid: None,
    )
    response = InstanceViewSet.as_view({"get": "network_topo"})(
        _req("get", superuser), model_id="switch", inst_uuid="550e8400-e29b-41d4-a716-446655440099"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_network_topo_404_when_instance_empty_dict(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda uid: {},
    )
    response = InstanceViewSet.as_view({"get": "network_topo"})(
        _req("get", superuser), model_id="switch", inst_uuid="550e8400-e29b-41d4-a716-446655440099"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


SWITCH_UUID = "550e8400-e29b-41d4-a716-446655440010"
ROUTER_UUID = "550e8400-e29b-41d4-a716-446655440011"


def _among(user, payload):
    return InstanceViewSet.as_view({"post": "network_topo_among"})(_req("post", user, payload))


@pytest.mark.django_db
def test_network_topo_among_returns_closed_set(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {"_id": 1, "model_id": "switch", "inst_uuid": uuids[0]},
            {"_id": 2, "model_id": "router", "inst_uuid": uuids[1]},
        ],
    )
    captured = {}

    def _fake(inst_uuids, permission_maps=None, user=None):
        captured["inst_uuids"] = list(inst_uuids)
        captured["models"] = sorted((permission_maps or {}).keys())
        captured["user"] = user
        return {
            "nodes": [
                {"id": SWITCH_UUID, "model_id": "switch"},
                {"id": ROUTER_UUID, "model_id": "router"},
            ],
            "links": [{"relationship_id": "9", "source_device": SWITCH_UUID, "target_device": ROUTER_UUID}],
            "truncated": False,
        }

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.network_topology_among_uuids", _fake)
    response = _among(superuser, {"inst_uuids": [SWITCH_UUID, ROUTER_UUID]})
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert {node["id"] for node in body["data"]["nodes"]} == {SWITCH_UUID, ROUTER_UUID}
    assert body["data"]["links"][0]["relationship_id"] == "9"
    assert "center" not in body["data"]
    assert captured["inst_uuids"] == [SWITCH_UUID, ROUTER_UUID]
    assert captured["models"] == ["router", "switch"]
    assert captured["user"] == superuser


@pytest.mark.django_db
def test_network_topo_among_rejects_non_list_empty_and_over_limit(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: (_ for _ in ()).throw(AssertionError("should not query")),
    )
    non_list = _among(superuser, {"inst_uuids": "switch"})
    empty = _among(superuser, {"inst_uuids": []})
    over = _among(
        superuser,
        {"inst_uuids": [f"00000000-0000-4000-8000-{index:012d}" for index in range(NETWORK_TOPO_NODE_LIMIT + 1)]},
    )
    assert non_list.status_code == status.HTTP_400_BAD_REQUEST
    assert empty.status_code == status.HTTP_400_BAD_REQUEST
    assert over.status_code == status.HTTP_400_BAD_REQUEST
    assert f"不能超过 {NETWORK_TOPO_NODE_LIMIT}" in _body(over)["message"]


@pytest.mark.django_db
def test_network_topo_among_maps_closed_set_rejection(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [{"_id": 1, "model_id": "host", "inst_uuid": uuids[0]}],
    )

    def _reject(*args, **kwargs):
        raise BaseAppException("设备列表包含无效或不允许的网络设备，请重新配置")

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.network_topology_among_uuids", _reject)
    response = _among(superuser, {"inst_uuids": [SWITCH_UUID]})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert _body(response)["message"] == "设备列表包含无效或不允许的网络设备，请重新配置"


@pytest.mark.django_db
def test_network_topo_among_stops_when_one_device_is_denied(superuser, monkeypatch):
    from apps.core.utils.web_utils import WebUtils

    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {"_id": 1, "model_id": "switch", "inst_uuid": uuids[0]},
            {"_id": 2, "model_id": "router", "inst_uuid": uuids[1]},
        ],
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceViewSet.require_instance_permission",
        lambda self, request, instance, operator=None: WebUtils.response_error(
            "无权限",
            status_code=status.HTTP_403_FORBIDDEN,
        ),
    )
    called = {"n": 0}

    def _fake(*args, **kwargs):
        called["n"] += 1
        return {"nodes": [], "links": []}

    monkeypatch.setattr(f"{VIEWS}.InstanceManage.network_topology_among_uuids", _fake)
    response = _among(superuser, {"inst_uuids": [SWITCH_UUID, ROUTER_UUID]})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert called["n"] == 0
