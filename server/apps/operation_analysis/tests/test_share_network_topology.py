import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.operation_analysis.models.models import Directory, NetworkTopology
from apps.operation_analysis.models.share_models import DashboardShareLink
from apps.operation_analysis.services.share_service import (
    create_or_get_share,
    exchange_share,
)
from apps.system_mgmt.models.user import User


@pytest.fixture
def sharer(db):
    User.objects.create(
        username="nt-sharer",
        domain="domain.com",
        display_name="Sharer",
        email="nt-sharer@example.com",
        password="x",
        group_list=[{"id": 1}],
    )
    return SimpleNamespace(
        id=1,
        pk=1,
        username="nt-sharer",
        domain="domain.com",
        disabled=False,
        is_superuser=True,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 1}],
    )


@pytest.fixture
def visitor(db):
    User.objects.create(
        username="nt-visitor",
        domain="other.com",
        display_name="Visitor",
        email="nt-visitor@example.com",
        password="x",
        group_list=[{"id": 99}],
    )
    return SimpleNamespace(
        id=2,
        pk=2,
        username="nt-visitor",
        domain="other.com",
        disabled=False,
        is_superuser=False,
        is_authenticated=True,
        locale="zh-Hans",
        group_list=[{"id": 99}],
    )


def _make_network_topology(**overrides):
    directory = Directory.objects.create(
        name=f"nt-dir-{uuid.uuid4()}",
        groups=[1],
        created_by="alice",
    )
    defaults = {
        "name": f"nt-share-{uuid.uuid4()}",
        "directory": directory,
        "groups": [1],
        "domain": "domain.com",
        "created_by": "alice",
        "base_url": "https://weops.example.com",
        "token": "super-secret-weops-token",
        "view_sets": {
            "nodes": [],
            "links": [],
        },
    }
    defaults.update(overrides)
    return NetworkTopology.objects.create(**defaults)


@pytest.mark.django_db
def test_create_network_topology_share_success(settings, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    topology = _make_network_topology()
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["resource_type"] == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert "/ops-analysis/share/" in response.data["url"]
    link = DashboardShareLink.objects.get(id=response.data["id"])
    assert link.resource_type == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert link.dashboard_instance_id == topology.pk
    assert link.dashboard_id is None


@pytest.mark.django_db
def test_network_topology_prepare_exchange_session_detail_without_token(
    settings, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    store = {}

    def cache_add(key, value, timeout=None):
        if key in store:
            return False
        store[key] = value
        return True

    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.set",
        lambda key, value, timeout=None: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.get",
        lambda key, default=None: store.get(key, default),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.delete",
        lambda key: store.pop(key, None) is not None,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.add",
        cache_add,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.cache.incr",
        lambda key: store.__setitem__(key, int(store.get(key, 0)) + 1) or store[key],
    )

    topology = _make_network_topology()
    sharer_client = APIClient()
    sharer_client.force_authenticate(sharer)
    sharer_client.cookies["current_team"] = "1"
    created = sharer_client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert created.status_code == 200
    token = created.data["url"].rsplit("/", 1)[-1]

    browser = APIClient()
    prepared = browser.post(
        "/api/v1/operation_analysis/api/dashboard_share/prepare/",
        {"token": token},
        format="json",
    )
    assert prepared.status_code == 200
    nonce = prepared.cookies["bk_dashboard_share_prep"].value
    state = prepared.data["state"]

    browser.force_authenticate(visitor)
    exchanged = browser.post(
        "/api/v1/operation_analysis/api/dashboard_share/exchange/",
        {"state": state},
        format="json",
        HTTP_COOKIE=f"bk_dashboard_share_prep={nonce}",
    )
    assert exchanged.status_code == 200, exchanged.data
    session_id = exchanged.data["session_id"]

    detail = browser.get(f"/api/v1/operation_analysis/api/dashboard_share/session/{session_id}/")
    assert detail.status_code == 200
    assert detail.data["resource_type"] == DashboardShareLink.ResourceType.NETWORK_TOPOLOGY
    assert detail.data["id"] == topology.id
    assert detail.data["view_sets"] == {"nodes": [], "links": []}
    assert "token" not in detail.data
    assert "base_url" not in detail.data
    assert "last_runtime_cache" not in detail.data
    assert "token_set" not in detail.data
    serialized = str(detail.data)
    assert "super-secret-weops-token" not in serialized
    assert "weops.example.com" not in serialized


@pytest.mark.django_db
def test_network_topology_share_rejects_without_view_permission(settings, sharer, monkeypatch):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: False,
    )
    topology = _make_network_topology()
    client = APIClient()
    client.force_authenticate(sharer)
    client.cookies["current_team"] = "1"
    response = client.post(
        f"/api/v1/operation_analysis/api/network_topology/{topology.id}/share/",
        {},
        format="json",
    )
    assert response.status_code == 403
    assert not DashboardShareLink.objects.filter(
        resource_type=DashboardShareLink.ResourceType.NETWORK_TOPOLOGY,
        dashboard_instance_id=topology.pk,
        status=DashboardShareLink.Status.ACTIVE,
    ).exists()


@pytest.mark.django_db
def test_network_topology_session_rejects_datasource_query(
    settings, sharer, visitor, monkeypatch
):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    topology = _make_network_topology()
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.NETWORK_TOPOLOGY,
        resource=topology,
        sharer=sharer,
        tenant_domain=topology.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    client = APIClient()
    client.force_authenticate(visitor)
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/{session.session_id}/query/1/",
        {},
        format="json",
    )
    assert response.status_code == 403


def _node(node_id, bk_inst_id=10001, *, with_metric=True, metric_overrides=None):
    node = {
        "id": node_id,
        "bk_obj_id": "bk_switch",
        "bk_inst_id": bk_inst_id,
        "bk_inst_name": f"switch-{bk_inst_id}",
        "ip_addr": "10.0.0.1",
        "network_collect_task_id": 12,
        "network_collect_instance_id": 345,
        "plugin_group_id": 3,
        "plugin_template_id": "tpl-1",
        "position": {"x": 10, "y": 20},
        "metrics": [],
    }
    if with_metric:
        metric = {
            "metric_field": "cpu_usage",
            "result_table_id": "rt.cpu",
            "display_name": "CPU",
            "unit": "%",
            "thresholds": [],
            "dimensions": {"ifName": "GigE0/1"},
            "condition_filter": [{"dimension_id": "ifName", "value": ["GigE0/1"]}],
            "display_mode": "dimension",
            "aggregate_type": "max",
        }
        if metric_overrides:
            metric.update(metric_overrides)
        node["metrics"] = [metric]
    return node


def _link(link_id="link-1", source="node-1", target="node-2"):
    return {
        "id": link_id,
        "source_node_id": source,
        "target_node_id": target,
        "is_draft": False,
        "port_pairs": [
            {
                "source_interface": {
                    "bk_obj_id": "bk_interface",
                    "bk_inst_id": 90001,
                    "interface_name": "GigE0/1",
                },
                "target_interface": {
                    "bk_obj_id": "bk_interface",
                    "bk_inst_id": 90002,
                    "interface_name": "GigE0/1",
                },
            }
        ],
        "interface_metrics": ["ifInOctets_5min"],
    }


def _open_nt_session(settings, sharer, visitor, monkeypatch, topology):
    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.NETWORK_TOPOLOGY,
        resource=topology,
        sharer=sharer,
        tenant_domain=topology.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    client = APIClient()
    client.force_authenticate(visitor)
    return client, session


@pytest.mark.django_db
def test_share_nt_metric_values_and_link_runtime_success(
    settings, sharer, visitor, monkeypatch
):
    topology = _make_network_topology(
        view_sets={
            "nodes": [_node("node-1", 10001), _node("node-2", 10002)],
            "links": [_link()],
        }
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)

    captured = {}

    class FakeAdapter:
        def batch_metric_values(self, items):
            captured["metric_items"] = items
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "status": "ok",
                        "value": 42,
                    }
                ]
            }

    def fake_build_link_runtime(topology_obj, adapter, link_payload, nodes_payload=None):
        captured["link"] = link_payload
        captured["nodes"] = nodes_payload
        return {
            "result": True,
            "data": {
                "link": {
                    "id": link_payload["id"],
                    "status": "normal",
                },
                "node_interface_summary": {},
            },
        }

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: FakeAdapter(),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.NetworkTopologyRuntimeService.build_link_runtime_preview",
        fake_build_link_runtime,
    )

    metric_body = {
        "items": [
            {
                "request_id": "node-1:cpu_usage",
                "node_ref": {
                    "bk_obj_id": "bk_switch",
                    "bk_inst_id": 10001,
                    "network_collect_task_id": 12,
                    "network_collect_instance_id": 345,
                    "plugin_template_id": "tpl-1",
                },
                "metric_ref": {"metric_field": "cpu_usage", "result_table_id": "rt.cpu"},
            }
        ]
    }
    metric_resp = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        metric_body,
        format="json",
    )
    assert metric_resp.status_code == 200, metric_resp.data
    assert metric_resp.data["items"][0]["value"] == 42
    assert captured["metric_items"][0]["node_ref"]["bk_inst_id"] == 10001
    assert captured["metric_items"][0]["dimensions"] == {"ifName": "GigE0/1"}
    assert captured["metric_items"][0]["condition_filter"] == [
        {"dimension_id": "ifName", "value": ["GigE0/1"]}
    ]
    assert captured["metric_items"][0]["display_mode"] == "dimension"
    assert captured["metric_items"][0]["aggregate_type"] == "max"
    assert "super-secret-weops-token" not in str(metric_resp.data)
    assert "token" not in metric_resp.data
    assert "base_url" not in metric_resp.data

    link_resp = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/link_runtime/",
        {
            "link": topology.view_sets["links"][0],
            "nodes": topology.view_sets["nodes"],
        },
        format="json",
    )
    assert link_resp.status_code == 200, link_resp.data
    assert link_resp.data["link"]["id"] == "link-1"
    assert captured["link"]["id"] == "link-1"
    assert {n["id"] for n in captured["nodes"]} == {"node-1", "node-2"}
    assert "super-secret-weops-token" not in str(link_resp.data)
    assert "token" not in link_resp.data
    assert "base_url" not in link_resp.data

@pytest.mark.django_db
def test_dashboard_session_cannot_call_nt_runtime_proxy(
    settings, sharer, visitor, monkeypatch
):
    from apps.operation_analysis.models.models import Dashboard

    settings.DASHBOARD_SHARE_SIGNING_KEY = "test-signing-key-at-least-32-bytes"
    monkeypatch.setattr(
        "apps.operation_analysis.services.share_service.can_view_canvas",
        lambda **_: True,
    )
    directory = Directory.objects.create(
        name=f"dash-dir-{uuid.uuid4()}", groups=[1], created_by="alice"
    )
    dashboard = Dashboard.objects.create(
        name=f"dash-{uuid.uuid4()}",
        directory=directory,
        groups=[1],
        created_by="alice",
        domain="domain.com",
        view_sets=[],
    )
    result = create_or_get_share(
        resource_type=DashboardShareLink.ResourceType.DASHBOARD,
        resource=dashboard,
        sharer=sharer,
        tenant_domain=dashboard.domain,
        space_id=1,
    )
    session = exchange_share(token=result.token, visitor=visitor)
    client = APIClient()
    client.force_authenticate(visitor)

    metric_resp = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        {"items": []},
        format="json",
    )
    link_resp = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/link_runtime/",
        {"link": {"id": "x"}},
        format="json",
    )
    assert metric_resp.status_code == 403
    assert link_resp.status_code == 403


@pytest.mark.django_db
def test_share_nt_rejects_tampered_node_ref(settings, sharer, visitor, monkeypatch):
    topology = _make_network_topology(
        view_sets={"nodes": [_node("node-1", 10001)], "links": []}
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)
    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: (_ for _ in ()).throw(AssertionError("should not call adapter")),
    )
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        {
            "items": [
                {
                    "request_id": "evil",
                    "node_ref": {
                        "bk_obj_id": "bk_switch",
                        "bk_inst_id": 99999,
                        "network_collect_task_id": 12,
                        "network_collect_instance_id": 345,
                        "plugin_template_id": "tpl-1",
                    },
                    "metric_ref": {"metric_field": "cpu_usage", "result_table_id": "rt.cpu"},
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_share_nt_uses_stored_metric_query_params(settings, sharer, visitor, monkeypatch):
    """客户端篡改 dimensions/condition_filter/display_mode/aggregate_type 时仍转发画布配置。"""
    topology = _make_network_topology(
        view_sets={"nodes": [_node("node-1", 10001)], "links": []}
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)
    captured = {}

    class FakeAdapter:
        def batch_metric_values(self, items):
            captured["items"] = items
            return {"items": [{"request_id": items[0]["request_id"], "status": "ok", "value": 1}]}

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: FakeAdapter(),
    )
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        {
            "items": [
                {
                    "request_id": "tamper",
                    "node_ref": {
                        "bk_obj_id": "bk_switch",
                        "bk_inst_id": 10001,
                        "network_collect_task_id": 12,
                        "network_collect_instance_id": 345,
                        "plugin_template_id": "tpl-1",
                    },
                    "metric_ref": {"metric_field": "cpu_usage", "result_table_id": "rt.cpu"},
                    "dimensions": {},
                    "condition_filter": [],
                    "display_mode": "aggregate",
                    "aggregate_type": "sum",
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    forwarded = captured["items"][0]
    assert forwarded["dimensions"] == {"ifName": "GigE0/1"}
    assert forwarded["condition_filter"] == [{"dimension_id": "ifName", "value": ["GigE0/1"]}]
    assert forwarded["display_mode"] == "dimension"
    assert forwarded["aggregate_type"] == "max"


@pytest.mark.django_db
def test_share_nt_rejects_undeclared_metric_ref(settings, sharer, visitor, monkeypatch):
    topology = _make_network_topology(
        view_sets={"nodes": [_node("node-1", 10001)], "links": []}
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)
    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: (_ for _ in ()).throw(AssertionError("should not call adapter")),
    )
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        {
            "items": [
                {
                    "request_id": "evil-metric",
                    "node_ref": {
                        "bk_obj_id": "bk_switch",
                        "bk_inst_id": 10001,
                        "network_collect_task_id": 12,
                        "network_collect_instance_id": 345,
                        "plugin_template_id": "tpl-1",
                    },
                    "metric_ref": {
                        "metric_field": "mem_usage",
                        "result_table_id": "rt.mem",
                    },
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_share_nt_rejects_tampered_link(settings, sharer, visitor, monkeypatch):
    topology = _make_network_topology(
        view_sets={
            "nodes": [_node("node-1", 10001), _node("node-2", 10002)],
            "links": [_link()],
        }
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)
    monkeypatch.setattr(
        "apps.operation_analysis.views.share_view.NetworkTopologyRuntimeService.build_link_runtime_preview",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not build")),
    )
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/link_runtime/",
        {
            "link": _link(link_id="link-evil", source="node-1", target="node-2"),
            "nodes": topology.view_sets["nodes"],
        },
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_share_nt_runtime_response_excludes_canvas_token(
    settings, sharer, visitor, monkeypatch
):
    topology = _make_network_topology(
        view_sets={"nodes": [_node("node-1", 10001)], "links": []}
    )
    client, session = _open_nt_session(settings, sharer, visitor, monkeypatch, topology)

    class FakeAdapter:
        def batch_metric_values(self, items):
            return {"items": [{"request_id": items[0]["request_id"], "status": "ok", "value": 1}]}

    monkeypatch.setattr(
        "apps.operation_analysis.views.network_topology_view._adapter_for",
        lambda topology_obj: FakeAdapter(),
    )
    response = client.post(
        f"/api/v1/operation_analysis/api/dashboard_share/session/"
        f"{session.session_id}/network_topology/metric_values/",
        {
            "items": [
                {
                    "request_id": "r1",
                    "node_ref": {
                        "bk_obj_id": "bk_switch",
                        "bk_inst_id": 10001,
                        "network_collect_task_id": 12,
                        "network_collect_instance_id": 345,
                        "plugin_template_id": "tpl-1",
                    },
                    "metric_ref": {"metric_field": "cpu_usage", "result_table_id": "rt.cpu"},
                }
            ]
        },
        format="json",
    )
    assert response.status_code == 200
    blob = str(response.data)
    assert "super-secret-weops-token" not in blob
    assert "weops.example.com" not in blob
    assert "token" not in response.data
    assert "base_url" not in response.data
