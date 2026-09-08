import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.views.alert import AlertModelViewSet
from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES, NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.operation_analysis.serializers.scene_widget_serializers import NetworkStatusTopologyRequestSerializer
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

SWITCH_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROUTER_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _post_request(user, data):
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/network_status_topology/",
        data=data,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _topology_request():
    return SimpleNamespace(
        user=SimpleNamespace(
            username="testuser",
            domain="domain.com",
            locale="en",
            timezone="Asia/Shanghai",
            permission={},
            group_tree=[],
            is_superuser=False,
        ),
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def test_request_serializer_defaults_node_limit_and_rejects_invalid_params():
    serializer = NetworkStatusTopologyRequestSerializer(data={"inst_uuids": [SWITCH_UUID]})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {
        "inst_uuids": [SWITCH_UUID],
        "node_limit": NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES,
    }

    for payload in (
        {"inst_uuids": []},
        {"inst_uuids": [SWITCH_UUID, SWITCH_UUID]},
        {"inst_uuids": [SWITCH_UUID], "node_limit": 0},
        {"inst_uuids": [SWITCH_UUID], "node_limit": NETWORK_STATUS_TOPOLOGY_MAX_NODES + 1},
        {"inst_uuids": ["not-a-uuid"]},
        {
            "inst_uuids": [SWITCH_UUID, ROUTER_UUID],
            "node_limit": 1,
        },
        {"model_id": "switch", "inst_uuid": SWITCH_UUID, "depth": 2},
    ):
        invalid = NetworkStatusTopologyRequestSerializer(data=payload)
        assert not invalid.is_valid(), payload


def test_build_returns_closed_set_without_center_or_alert_fields(monkeypatch):
    topology = {
        "nodes": [
            {"id": SWITCH_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
            {"id": ROUTER_UUID, "model_id": "router", "name": "edge-router", "hop": 0},
        ],
        "links": [{"relationship_id": "rel-1", "source_device": SWITCH_UUID, "target_device": ROUTER_UUID}],
        "truncated": False,
    }
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        classmethod(lambda cls, request, inst_uuids: topology),
    )

    result = NetworkStatusTopologyService.build(
        request=_topology_request(),
        inst_uuids=[SWITCH_UUID, ROUTER_UUID],
        node_limit=100,
    )

    assert "center_id" not in result
    assert result["links"] == topology["links"]
    assert result["truncated"] is False
    assert result["node_limit"] == 100
    assert [node["id"] for node in result["nodes"]] == [SWITCH_UUID, ROUTER_UUID]
    for node in result["nodes"]:
        assert "status" not in node
        assert "alert_count" not in node
        assert "pulse" not in node
        assert "severity" not in node
        assert "color" not in node


def test_build_does_not_query_alerts(monkeypatch):
    topology = {
        "nodes": [
            {"id": SWITCH_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
        ],
        "links": [],
        "truncated": False,
    }
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        classmethod(lambda cls, request, inst_uuids: topology),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("scene topology must not query alert-center")

    monkeypatch.setattr(AlertModelViewSet, "get_queryset_by_permission", fail_if_called)
    monkeypatch.setattr(AlertModelViewSet, "get_queryset", fail_if_called)

    result = NetworkStatusTopologyService.build(
        request=_topology_request(),
        inst_uuids=[SWITCH_UUID],
        node_limit=100,
    )

    assert result["nodes"] == topology["nodes"]
    assert result["links"] == topology["links"]


@pytest.mark.django_db
def test_view_validates_request_and_calls_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    captured = {}

    def fake_build(request, inst_uuids, node_limit=None):
        captured["args"] = (request, inst_uuids, node_limit)
        return {
            "nodes": [],
            "links": [],
            "truncated": False,
            "node_limit": node_limit,
        }

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(authenticated_user, {"inst_uuids": [SWITCH_UUID, ROUTER_UUID]})
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["nodes"] == []
    assert captured["args"][1:] == ([SWITCH_UUID, ROUTER_UUID], NETWORK_STATUS_TOPOLOGY_DEFAULT_NODES)


@pytest.mark.django_db
def test_view_rejects_legacy_center_payload_without_calling_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    called = False

    def fake_build(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(
        authenticated_user,
        {"model_id": "switch", "inst_uuid": SWITCH_UUID, "depth": 2},
    )
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert called is False
    assert "inst_uuids" in payload["message"]


def test_build_calls_cmdb_rpc_with_user_info(monkeypatch):
    captured = {}
    topology = {
        "nodes": [{"id": SWITCH_UUID, "model_id": "switch", "name": "core-switch", "hop": 0}],
        "links": [{"relationship_id": "rel-1", "source_device": SWITCH_UUID, "target_device": ROUTER_UUID}],
        "truncated": False,
    }

    class FakeCMDB:
        def network_topology_among_uuids(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"result": True, "message": "", "data": topology}

    monkeypatch.setattr("apps.operation_analysis.services.network_status_topology.CMDB", FakeCMDB)

    result = NetworkStatusTopologyService.build(
        request=_topology_request(),
        inst_uuids=[SWITCH_UUID, ROUTER_UUID],
        node_limit=100,
    )

    assert captured["kwargs"]["inst_uuids"] == [SWITCH_UUID, ROUTER_UUID]
    assert captured["kwargs"]["user_info"]["team"] == 1
    assert captured["kwargs"]["user_info"]["user"] == "testuser"
    assert result["nodes"] == topology["nodes"]
    assert result["links"] == topology["links"]
    assert result["truncated"] is False
    assert result["node_limit"] == 100
    assert "center_id" not in result


def test_build_maps_nats_failure_to_closed_set_error(monkeypatch):
    class FakeCMDB:
        def network_topology_among_uuids(self, **kwargs):
            return {
                "result": False,
                "data": {"nodes": [], "links": []},
                "message": "inst_uuids 不能超过 200",
            }

    monkeypatch.setattr("apps.operation_analysis.services.network_status_topology.CMDB", FakeCMDB)

    with pytest.raises(ValidationError) as exc_info:
        NetworkStatusTopologyService.build(
            request=_topology_request(),
            inst_uuids=[SWITCH_UUID],
            node_limit=100,
        )

    assert NetworkStatusTopologyService.CLOSED_SET_ERROR in str(exc_info.value.detail)


def test_build_does_not_map_rpc_errors_to_closed_set(monkeypatch):
    class FakeCMDB:
        def network_topology_among_uuids(self, **kwargs):
            raise RuntimeError("nats unavailable")

    monkeypatch.setattr("apps.operation_analysis.services.network_status_topology.CMDB", FakeCMDB)

    with pytest.raises(RuntimeError, match="nats unavailable"):
        NetworkStatusTopologyService.build(
            request=_topology_request(),
            inst_uuids=[SWITCH_UUID],
            node_limit=100,
        )
