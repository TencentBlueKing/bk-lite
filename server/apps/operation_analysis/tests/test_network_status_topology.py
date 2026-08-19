import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.views.alert import AlertModelViewSet
from apps.cmdb.constants.constants import NETWORK_TOPO_DEFAULT_HOP, NETWORK_TOPO_MAX_HOP, VIEW
from apps.operation_analysis.serializers.scene_widget_serializers import NetworkStatusTopologyRequestSerializer
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
HOST_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


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


def test_request_serializer_defaults_depth_and_rejects_invalid_params():
    serializer = NetworkStatusTopologyRequestSerializer(data={"model_id": "switch", "inst_uuid": CENTER_UUID})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {
        "model_id": "switch",
        "inst_uuid": UUID(CENTER_UUID),
        "depth": NETWORK_TOPO_DEFAULT_HOP,
    }

    for payload in (
        {"model_id": "switch", "inst_uuid": CENTER_UUID, "depth": 0},
        {"model_id": "switch", "inst_uuid": CENTER_UUID, "depth": NETWORK_TOPO_MAX_HOP + 1},
        {"model_id": "", "inst_uuid": CENTER_UUID, "depth": 2},
        {"model_id": "switch", "inst_uuid": "not-a-uuid", "depth": 2},
    ):
        invalid = NetworkStatusTopologyRequestSerializer(data=payload)
        assert not invalid.is_valid()


def test_build_returns_topology_structure_without_alert_fields(monkeypatch, authenticated_user):
    topology = {
        "center": {"id": CENTER_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
        "nodes": [
            {"id": CENTER_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
            {"id": HOST_UUID, "model_id": "host", "name": "biz-host", "hop": 1},
        ],
        "links": [{"relationship_id": "rel-1", "source_device": CENTER_UUID, "target_device": HOST_UUID}],
        "truncated": False,
    }
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        staticmethod(lambda request, model_id, inst_uuid, depth: topology),
    )

    result = NetworkStatusTopologyService.build(
        request=SimpleNamespace(user=authenticated_user),
        model_id="switch",
        inst_uuid=CENTER_UUID,
        depth=2,
    )

    assert result["center_id"] == CENTER_UUID
    assert result["center_model_id"] == "switch"
    assert result["links"] == topology["links"]
    assert result["truncated"] is False
    for node in result["nodes"]:
        assert "status" not in node
        assert "alert_count" not in node
        assert "pulse" not in node
        assert "severity" not in node
        assert "color" not in node


def test_build_does_not_query_alerts(monkeypatch, authenticated_user):
    topology = {
        "center": {"id": CENTER_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
        "nodes": [
            {"id": CENTER_UUID, "model_id": "switch", "name": "core-switch", "hop": 0},
        ],
        "links": [],
        "truncated": False,
    }
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        staticmethod(lambda request, model_id, inst_uuid, depth: topology),
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("scene topology must not query alert-center")

    monkeypatch.setattr(AlertModelViewSet, "get_queryset_by_permission", fail_if_called)
    monkeypatch.setattr(AlertModelViewSet, "get_queryset", fail_if_called)

    result = NetworkStatusTopologyService.build(
        request=SimpleNamespace(user=authenticated_user),
        model_id="switch",
        inst_uuid=CENTER_UUID,
        depth=2,
    )

    assert result["nodes"] == topology["nodes"]
    assert result["links"] == topology["links"]


def test_get_cmdb_topology_reuses_cmdb_permission_flow(monkeypatch, authenticated_user):
    captured = {}

    def fake_require_instance_permission(self, request, instance, operator):
        captured["permission"] = (request, instance, operator)
        return None

    def fake_format_user_groups_permissions(request, model_id):
        captured["permission_map_input"] = (request, model_id)
        return {"allowed": True}

    def fake_network_topology(inst_uuid, model_id, depth, permission_map, user):
        captured["network_topology"] = (inst_uuid, model_id, depth, permission_map, user)
        return {"center": {"id": str(inst_uuid), "model_id": model_id}, "nodes": [], "links": [], "truncated": False}

    request = SimpleNamespace(user=authenticated_user)
    instance = {"id": 100, "inst_uuid": CENTER_UUID, "model_id": "switch", "inst_name": "core-switch"}
    monkeypatch.setattr(
        "apps.operation_analysis.services.network_status_topology.InstanceManage.query_entity_by_uuid",
        lambda inst_uuid: instance,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.network_status_topology.InstanceViewSet.require_instance_permission",
        fake_require_instance_permission,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.network_status_topology.CmdbRulesFormatUtil.format_user_groups_permissions",
        fake_format_user_groups_permissions,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.network_status_topology.InstanceManage.network_topology_by_uuid",
        fake_network_topology,
    )

    result = NetworkStatusTopologyService._get_cmdb_topology(request, "ignored-model", CENTER_UUID, 2)

    assert result["center"]["model_id"] == "switch"
    assert captured["permission"] == (request, instance, VIEW)
    assert captured["permission_map_input"] == (request, "switch")
    assert captured["network_topology"] == (CENTER_UUID, "switch", 2, {"allowed": True}, authenticated_user)


@pytest.mark.django_db
def test_view_validates_request_and_calls_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    captured = {}

    def fake_build(request, model_id, inst_uuid, depth):
        captured["args"] = (request, model_id, inst_uuid, depth)
        return {
            "center_id": str(inst_uuid),
            "center_model_id": model_id,
            "nodes": [],
            "links": [],
            "truncated": False,
        }

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(authenticated_user, {"model_id": "switch", "inst_uuid": CENTER_UUID})
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["center_id"] == CENTER_UUID
    assert captured["args"][1:] == ("switch", CENTER_UUID, NETWORK_TOPO_DEFAULT_HOP)


@pytest.mark.django_db
def test_view_rejects_invalid_request_without_calling_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    called = False

    def fake_build(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(authenticated_user, {"model_id": "switch", "inst_uuid": CENTER_UUID, "depth": 0})
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "depth" in payload["message"]
    assert called is False
