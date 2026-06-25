import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.constants import AlertStatus
from apps.alerts.models.models import Alert
from apps.alerts.views.alert import AlertModelViewSet
from apps.cmdb.constants.constants import NETWORK_TOPO_DEFAULT_HOP, NETWORK_TOPO_MAX_HOP, VIEW
from apps.operation_analysis.serializers.scene_widget_serializers import NetworkStatusTopologyRequestSerializer
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService, map_alert_level_to_node_status
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet


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


def test_map_alert_level_to_node_status():
    assert map_alert_level_to_node_status(None) == {
        "status": "normal",
        "severity": None,
        "pulse": False,
        "color": "green",
    }
    assert map_alert_level_to_node_status("2") == {
        "status": "warning",
        "severity": "warning",
        "pulse": False,
        "color": "yellow",
    }
    assert map_alert_level_to_node_status("1") == {
        "status": "error",
        "severity": "error",
        "pulse": False,
        "color": "red",
    }
    assert map_alert_level_to_node_status("0") == {
        "status": "critical",
        "severity": "critical",
        "pulse": True,
        "color": "red",
    }


def test_request_serializer_defaults_depth_and_rejects_invalid_params():
    serializer = NetworkStatusTopologyRequestSerializer(data={"model_id": "switch", "inst_id": "100"})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data == {
        "model_id": "switch",
        "inst_id": 100,
        "depth": NETWORK_TOPO_DEFAULT_HOP,
    }

    for payload in (
        {"model_id": "switch", "inst_id": "100", "depth": 0},
        {"model_id": "switch", "inst_id": "100", "depth": NETWORK_TOPO_MAX_HOP + 1},
        {"model_id": "", "inst_id": "100", "depth": 2},
        {"model_id": "switch", "inst_id": "not-an-int", "depth": 2},
    ):
        invalid = NetworkStatusTopologyRequestSerializer(data=payload)
        assert not invalid.is_valid()


def test_build_merges_topology_structure_with_alert_status(monkeypatch, authenticated_user):
    topology = {
        "center": {"id": "100", "model_id": "switch", "name": "core-switch", "hop": 0},
        "nodes": [
            {"id": "100", "model_id": "switch", "name": "core-switch", "hop": 0, "expanded": True},
            {"id": "200", "model_id": "host", "name": "biz-host", "hop": 1, "expanded": False},
        ],
        "links": [
            {
                "relationship_id": "rel-1",
                "source_device": "100",
                "source_inst_name": "Gi0/1",
                "target_device": "200",
                "target_inst_name": "eth0",
                "asst_id": "connect",
            }
        ],
        "truncated": False,
    }

    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_cmdb_topology",
        staticmethod(lambda request, model_id, inst_id, depth: topology),
    )
    monkeypatch.setattr(
        NetworkStatusTopologyService,
        "_get_active_alert_summary",
        staticmethod(lambda request, node_keys: {("host", "200"): {"count": 2, "max_level": "0"}}),
    )

    result = NetworkStatusTopologyService.build(
        request=SimpleNamespace(user=authenticated_user),
        model_id="switch",
        inst_id=100,
        depth=2,
    )

    assert result["center_id"] == "100"
    assert result["center_model_id"] == "switch"
    assert result["truncated"] is False
    assert result["nodes"][0]["alert_count"] == 0
    assert result["nodes"][0]["status"] == "normal"
    assert result["nodes"][1]["alert_count"] == 2
    assert result["nodes"][1]["status"] == "critical"
    assert result["nodes"][1]["pulse"] is True
    assert result["links"] == topology["links"]


@pytest.mark.django_db
def test_active_alert_summary_uses_alert_permission_and_exact_resource_pairs(monkeypatch, authenticated_user):
    visible_critical = Alert.objects.create(
        alert_id="visible-critical",
        title="critical",
        content="critical",
        fingerprint="fp-critical",
        level="0",
        status=AlertStatus.UNASSIGNED,
        resource_type="host",
        resource_id="200",
    )
    visible_warning = Alert.objects.create(
        alert_id="visible-warning",
        title="warning",
        content="warning",
        fingerprint="fp-warning",
        level="2",
        status=AlertStatus.PENDING,
        resource_type="host",
        resource_id="200",
    )
    Alert.objects.create(
        alert_id="closed",
        title="closed",
        content="closed",
        fingerprint="fp-closed",
        level="0",
        status=AlertStatus.CLOSED,
        resource_type="host",
        resource_id="200",
    )
    Alert.objects.create(
        alert_id="cross-pair",
        title="cross pair",
        content="cross pair",
        fingerprint="fp-cross-pair",
        level="0",
        status=AlertStatus.UNASSIGNED,
        resource_type="host",
        resource_id="100",
    )

    calls = []

    def fake_get_queryset_by_permission(self, request, queryset, permission_key=None):
        calls.append((request, queryset.model, permission_key))
        return queryset.filter(id__in=[visible_critical.id, visible_warning.id])

    monkeypatch.setattr(AlertModelViewSet, "get_queryset_by_permission", fake_get_queryset_by_permission)

    result = NetworkStatusTopologyService._get_active_alert_summary(
        SimpleNamespace(user=authenticated_user),
        {("host", "200"), ("switch", "100")},
    )

    assert calls == [(calls[0][0], Alert, None)]
    assert result == {("host", "200"): {"count": 2, "max_level": "0"}}


def test_get_cmdb_topology_reuses_cmdb_permission_flow(monkeypatch, authenticated_user):
    captured = {}

    def fake_require_instance_permission(self, request, instance, operator):
        captured["permission"] = (request, instance, operator)
        return None

    def fake_format_user_groups_permissions(request, model_id):
        captured["permission_map_input"] = (request, model_id)
        return {"allowed": True}

    def fake_network_topology(inst_id, model_id, depth, permission_map, user):
        captured["network_topology"] = (inst_id, model_id, depth, permission_map, user)
        return {"center": {"id": str(inst_id), "model_id": model_id}, "nodes": [], "links": [], "truncated": False}

    request = SimpleNamespace(user=authenticated_user)
    instance = {"id": 100, "model_id": "switch", "inst_name": "core-switch"}
    monkeypatch.setattr(
        "apps.operation_analysis.services.network_status_topology.InstanceManage.query_entity_by_id",
        lambda inst_id: instance,
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
        "apps.operation_analysis.services.network_status_topology.InstanceManage.network_topology",
        fake_network_topology,
    )

    result = NetworkStatusTopologyService._get_cmdb_topology(request, "ignored-model", 100, 2)

    assert result["center"]["model_id"] == "switch"
    assert captured["permission"] == (request, instance, VIEW)
    assert captured["permission_map_input"] == (request, "switch")
    assert captured["network_topology"] == (100, "switch", 2, {"allowed": True}, authenticated_user)


@pytest.mark.django_db
def test_view_validates_request_and_calls_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    captured = {}

    def fake_build(request, model_id, inst_id, depth):
        captured["args"] = (request, model_id, inst_id, depth)
        return {
            "center_id": str(inst_id),
            "center_model_id": model_id,
            "nodes": [],
            "links": [],
            "truncated": False,
        }

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(authenticated_user, {"model_id": "switch", "inst_id": "100"})
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["center_id"] == "100"
    assert captured["args"][1:] == ("switch", 100, NETWORK_TOPO_DEFAULT_HOP)


@pytest.mark.django_db
def test_view_rejects_invalid_request_without_calling_service(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = True
    called = False

    def fake_build(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(NetworkStatusTopologyService, "build", staticmethod(fake_build))

    request = _post_request(authenticated_user, {"model_id": "switch", "inst_id": "100", "depth": 0})
    response = SceneWidgetViewSet.as_view({"post": "network_status_topology"})(request)
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "depth" in payload["message"]
    assert called is False
