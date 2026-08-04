from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore
from apps.apm.services import DjangoApmTopologyService, DjangoIngestSourceService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    SpanDetail,
    TopologyTarget,
    TraceDetail,
    TraceSummary,
)


def _telemetry(now, source_id=None):
    trace_id = "a" * 32
    summary = TraceSummary(trace_id, now, 30, "shop", "gateway", "prod", "gateway-1", "error", ingest_source_id=source_id)
    spans = (
        SpanDetail("1" * 16, None, "GET /checkout", now, 30, "ok", service_namespace="shop", service_name="gateway", environment="prod", instance_id="gateway-1", ingest_source_id=source_id),
        SpanDetail("2" * 16, "1" * 16, "POST /pay", now, 20, "error", service_namespace="shop", service_name="payment", environment="prod", instance_id="payment-1", ingest_source_id=source_id),
    )
    detail = TraceDetail(trace_id, spans, "shop", "gateway", "prod", "gateway-1", source_id)
    return summary, detail


def test_topology_builds_bounded_service_edges_from_real_trace_relationships():
    now = timezone.now()
    summary, detail = _telemetry(now)
    service = DjangoApmTopologyService(InMemoryTraceStore(summaries=[summary], details=[detail]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert graph.data_state == "available"
    assert graph.sampled_traces == 1
    assert [(node.service_name, node.health) for node in graph.nodes] == [
        ("gateway", "healthy"),
        ("payment", "critical"),
    ]
    assert len(graph.edges) == 1
    assert graph.edges[0].sampled_calls == graph.edges[0].error_calls == 1
    assert graph.edges[0].average_duration_ms == 20


@pytest.mark.django_db
def test_topology_api_only_queries_targets_visible_to_current_organization(apm_api_client, mocker):
    now = timezone.now()
    source = DjangoIngestSourceService().create(
        name="topology-source",
        ingest_type="otlp_http",
        organization_ids=[10],
        actor="tester",
    ).source
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery(source.id, "shop", "gateway", "gateway-1", "prod", seen_at=now))
    catalog.discover(CatalogDiscovery(source.id, "shop", "payment", "payment-1", "prod", seen_at=now))
    summary, detail = _telemetry(now, source.id)
    service = DjangoApmTopologyService(InMemoryTraceStore(summaries=[summary], details=[detail]))
    mocked = mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}
    mocked.assert_called_once_with()


@pytest.mark.django_db
def test_topology_api_uses_service_visibility_instead_of_instance_visibility(apm_api_client, mocker):
    now = timezone.now()
    source = DjangoIngestSourceService().create(
        name="instance-private-topology-source",
        ingest_type="otlp_http",
        organization_ids=[20],
        actor="tester",
    ).source
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(
        CatalogDiscovery(source.id, "shop", "gateway", "gateway-1", "prod", seen_at=now)
    )
    payment = catalog.discover(
        CatalogDiscovery(source.id, "shop", "payment", "payment-1", "prod", seen_at=now)
    )
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")
    catalog.set_service_organizations(payment.service.id, [10], actor="tester")

    summary, detail = _telemetry(now, source.id)
    service = DjangoApmTopologyService(InMemoryTraceStore(summaries=[summary], details=[detail]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}


@pytest.mark.django_db
def test_topology_api_does_not_leak_related_services_outside_service_scope(apm_api_client, mocker):
    now = timezone.now()
    source = DjangoIngestSourceService().create(
        name="cross-scope-topology-source",
        ingest_type="otlp_http",
        organization_ids=[20],
        actor="tester",
    ).source
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(
        CatalogDiscovery(source.id, "shop", "gateway", "gateway-1", "prod", seen_at=now)
    )
    catalog.discover(
        CatalogDiscovery(source.id, "shop", "payment", "payment-1", "prod", seen_at=now)
    )
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")

    summary, detail = _telemetry(now, source.id)
    service = DjangoApmTopologyService(InMemoryTraceStore(summaries=[summary], details=[detail]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert [node["service_name"] for node in response.data["nodes"]] == ["gateway"]
    assert not response.data["edges"]
