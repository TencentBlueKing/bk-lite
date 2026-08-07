from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore
from apps.apm.services import DjangoApmTopologyService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    ServiceDependency,
    SpanDetail,
    TopologyTarget,
    TraceDetail,
    TraceSummary,
)
from apps.apm.tests.helpers import create_application


def _telemetry(now):
    trace_id = "a" * 32
    summary = TraceSummary(trace_id, now, 30, "shop", "gateway", "prod", "gateway-1", "error")
    spans = (
        SpanDetail("1" * 16, None, "GET /checkout", now, 30, "ok", service_namespace="shop", service_name="gateway", environment="prod", instance_id="gateway-1"),
        SpanDetail("2" * 16, "1" * 16, "POST /pay", now, 20, "error", service_namespace="shop", service_name="payment", environment="prod", instance_id="payment-1"),
    )
    detail = TraceDetail(trace_id, spans, "shop", "gateway", "prod", "gateway-1")
    return summary, detail


def test_topology_builds_bounded_service_edges_from_real_trace_relationships():
    now = timezone.now()
    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 25)])
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert graph.data_state == "available"
    assert graph.sampled_traces == 25
    assert [(node.service_name, node.health) for node in graph.nodes] == [
        ("gateway", "unknown"),
        ("payment", "unknown"),
    ]
    assert len(graph.edges) == 1
    assert graph.edges[0].sampled_calls == 25
    assert graph.edges[0].error_calls == 0
    assert graph.edges[0].average_duration_ms == 0


@pytest.mark.django_db
def test_topology_api_only_queries_targets_visible_to_current_organization(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now))
    catalog.discover(CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now))
    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 1)])
    )
    mocked = mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}
    mocked.assert_called_once_with()


@pytest.mark.django_db
def test_topology_api_uses_service_visibility_instead_of_instance_visibility(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (20,))
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(
        CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now)
    )
    payment = catalog.discover(
        CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now)
    )
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")
    catalog.set_service_organizations(payment.service.id, [10], actor="tester")

    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 1)])
    )
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}


@pytest.mark.django_db
def test_topology_api_does_not_leak_related_services_outside_service_scope(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (20,))
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(
        CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now)
    )
    catalog.discover(
        CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now)
    )
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")

    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 1)])
    )
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 0
    assert not response.data["nodes"]
    assert not response.data["edges"]
    assert response.data["diagnostics"] == ("omitted_ambiguous_dependencies:1",)
