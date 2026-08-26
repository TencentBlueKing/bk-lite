from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, TelemetryStoreUnavailable
from apps.apm.services import DjangoApmTopologyService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    ServiceDependency,
    ServiceMetricQuery,
    ServiceRed,
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
    assert graph.nodes[0].request_rate is None
    assert graph.nodes[0].error_rate is None
    assert graph.nodes[0].p95_ms is None


class _RedByServiceName:
    def __init__(self, reds: dict[str, ServiceRed], *, fail_for: str = ""):
        self.reds = reds
        self.fail_for = fail_for
        self.queries: list[ServiceMetricQuery] = []

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        self.queries.append(query)
        if query.service_name == self.fail_for:
            raise TelemetryStoreUnavailable("RED unavailable")
        return self.reds[query.service_name]


def test_topology_overlays_service_red_without_inventing_edge_latency():
    now = timezone.now()
    metric_store = _RedByServiceName(
        {
            "gateway": ServiceRed(request_rate=12.0, error_rate=0.0, p95_ms=40.0, p99_ms=80.0),
            "payment": ServiceRed(request_rate=4.0, error_rate=0.08, p95_ms=400.0, p99_ms=900.0),
        }
    )
    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 25)]),
        metric_store,
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    by_name = {node.service_name: node for node in graph.nodes}
    assert by_name["gateway"].health == "healthy"
    assert by_name["gateway"].request_rate == 12.0
    assert by_name["gateway"].error_rate == 0.0
    assert by_name["gateway"].p95_ms == 40.0
    assert by_name["payment"].health == "critical"
    assert by_name["payment"].error_rate == 0.08
    assert by_name["payment"].p95_ms == 400.0
    assert graph.edges[0].error_calls == 0
    assert graph.edges[0].average_duration_ms == 0


def test_topology_red_failure_keeps_graph_and_marks_node_unknown():
    now = timezone.now()
    metric_store = _RedByServiceName(
        {"gateway": ServiceRed(request_rate=3.0, error_rate=0.02, p95_ms=90.0, p99_ms=120.0)},
        fail_for="payment",
    )
    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 8)]),
        metric_store,
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    by_name = {node.service_name: node for node in graph.nodes}
    assert by_name["gateway"].health == "warning"
    assert by_name["payment"].health == "unknown"
    assert by_name["payment"].p95_ms is None
    assert graph.data_state == "available"


def test_topology_red_window_falls_back_to_24h_for_seven_day_query():
    now = timezone.now()
    metric_store = _RedByServiceName(
        {
            "gateway": ServiceRed(request_rate=1.0, error_rate=0.0, p95_ms=10.0, p99_ms=20.0),
            "payment": ServiceRed(request_rate=1.0, error_rate=0.0, p95_ms=12.0, p99_ms=18.0),
        }
    )
    service = DjangoApmTopologyService(
        InMemoryTraceStore(dependencies=[ServiceDependency("gateway", "payment", 1)]),
        metric_store,
    )
    started_at = now - timedelta(days=7)

    service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=started_at,
        ended_at=now,
    )

    assert metric_store.queries
    assert all(query.ended_at - query.started_at == timedelta(hours=24) for query in metric_store.queries)
    assert all(query.include_breakdown is False for query in metric_store.queries)


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
