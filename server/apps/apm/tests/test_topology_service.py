from datetime import timedelta
from logging import LogRecord
from pathlib import Path

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, TelemetryStoreUnavailable
from apps.apm.adapters.span_aliases import format_peer_endpoint, infer_downstream
from apps.apm.models import ApmService
from apps.apm.services import DjangoApmTopologyService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery, SpanDetail, TopologySampleQuery, TopologyTarget, TraceDetail
from apps.apm.tests.helpers import create_application


def _span(
    span_id: str,
    parent: str | None,
    name: str,
    now,
    *,
    service: str,
    status: str = "ok",
    kind: str = "server",
    duration: float = 20,
    attrs: dict | None = None,
    environment: str = "prod",
    namespace: str = "shop",
):
    return SpanDetail(
        span_id,
        parent,
        name,
        now,
        duration,
        status,
        attributes=attrs or {},
        service_namespace=namespace,
        service_name=service,
        environment=environment,
        kind=kind,
    )


def _trace(trace_id: str, spans: tuple[SpanDetail, ...]):
    root = next((span for span in spans if span.parent_span_id is None), spans[0])
    return TraceDetail(trace_id, spans, root.service_namespace, root.service_name, root.environment, root.instance_id)


def _gateway_payment_trace(now, *, status="ok", trace_id="a" * 32):
    return _trace(
        trace_id,
        (
            _span("1" * 16, None, "GET /checkout", now, service="gateway", duration=30, status=status),
            _span(
                "2" * 16,
                "1" * 16,
                "POST /pay",
                now,
                service="gateway",
                kind="client",
                duration=20,
                status=status,
                attrs={"db.system": "mysql"},
            ),
            _span("3" * 16, "2" * 16, "POST /pay", now, service="payment", duration=18, status=status),
        ),
    )


def _mysql_client_trace(now, *, attr_key="db.system", trace_id="b" * 32, status="ok", extra_attrs=None):
    attrs = {attr_key: "mysql", **(extra_attrs or {})}
    return _trace(
        trace_id,
        (
            _span("4" * 16, None, "GET /checkout", now, service="gateway", duration=40, status=status),
            _span(
                "5" * 16,
                "4" * 16,
                "SELECT orders",
                now,
                service="gateway",
                kind="client",
                duration=12,
                status=status,
                attrs=attrs,
            ),
        ),
    )


def test_topology_builds_cross_service_edges_and_edge_red_from_the_same_sample():
    now = timezone.now()
    error_trace = _gateway_payment_trace(now, status="error", trace_id="e" * 32)
    ok_trace = _gateway_payment_trace(now - timedelta(seconds=1), status="ok", trace_id="o" * 32)
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[error_trace, ok_trace]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod", "go"), TopologyTarget("shop", "payment", "prod", "python")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert graph.data_state == "available"
    assert graph.sampled_traces == 2
    by_name = {node.service_name: node for node in graph.nodes}
    assert by_name["gateway"].kind == "instrumented"
    assert by_name["gateway"].health == "critical"
    assert by_name["gateway"].error_rate == 0.5
    assert by_name["gateway"].p95_ms == 30
    assert by_name["gateway"].request_rate is not None
    assert graph.edges[0].sampled_calls == 2
    assert graph.edges[0].error_calls == 1
    assert graph.edges[0].error_rate == 0.5
    assert graph.edges[0].p95_ms == 20
    assert graph.edges[0].health == "critical"


def test_topology_error_slice_drops_edges_only_present_on_ok_requests():
    now = timezone.now()
    ok_only = _trace(
        "k" * 32,
        (
            _span("1" * 16, None, "GET /checkout", now, service="gateway"),
            _span("2" * 16, "1" * 16, "GET /stock", now, service="gateway", kind="client"),
            _span("3" * 16, "2" * 16, "GET /stock", now, service="inventory"),
        ),
    )
    error_pay = _gateway_payment_trace(now, status="error", trace_id="e" * 32)
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[ok_only, error_pay]))

    graph = service.build(
        [
            TopologyTarget("shop", "gateway", "prod"),
            TopologyTarget("shop", "payment", "prod"),
            TopologyTarget("shop", "inventory", "prod"),
        ],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        status="error",
    )

    assert {(edge.source.split(":")[1], edge.target.split(":")[1]) for edge in graph.edges} == {("gateway", "payment")}


def test_topology_operation_slice_keeps_only_traces_that_hit_that_span():
    now = timezone.now()
    checkout = _gateway_payment_trace(now, trace_id="c" * 32)
    stock = _trace(
        "s" * 32,
        (
            _span("1" * 16, None, "GET /products", now, service="gateway"),
            _span("2" * 16, "1" * 16, "GET /stock", now, service="gateway", kind="client"),
            _span("3" * 16, "2" * 16, "GET /stock", now, service="inventory"),
        ),
    )
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[checkout, stock]))

    graph = service.build(
        [
            TopologyTarget("shop", "gateway", "prod"),
            TopologyTarget("shop", "payment", "prod"),
            TopologyTarget("shop", "inventory", "prod"),
        ],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        span_name="POST /pay",
    )

    names = {(edge.source.split(":")[1], edge.target.split(":")[1]) for edge in graph.edges}
    assert names == {("gateway", "payment")}


def test_topology_empty_sample_keeps_unknown_health_and_no_data_state():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore())

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert graph.data_state == "no_data"
    assert graph.nodes == ()
    assert graph.edges == ()
    assert graph.sampled_traces == 0


def test_db_system_or_db_system_name_alone_yields_inferred_mysql_node():
    now = timezone.now()
    for key in ("db.system", "db.system.name"):
        service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now, attr_key=key)]))
        graph = service.build(
            [TopologyTarget("shop", "gateway", "prod")],
            started_at=now - timedelta(hours=1),
            ended_at=now,
            include_inferred=True,
        )
        inferred = next(node for node in graph.nodes if node.kind == "inferred")
        assert inferred.service_name == "mysql"
        assert inferred.fold_key == "mysql"
        assert inferred.inferred_system == "mysql"
        assert inferred.request_rate is None
        assert graph.edges[0].sampled_calls == 1
        assert graph.edges[0].p95_ms == 12
        assert graph.edges[0].sample_traces[0].span_name == "SELECT orders"


def test_span_attr_prefixed_db_system_name_still_folds_to_mysql():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now, attr_key="span_attr:db.system.name")]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    assert {node.service_name for node in graph.nodes if node.kind == "inferred"} == {"mysql"}


def test_inferred_node_is_omitted_without_include_inferred_flag():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert graph.nodes == ()
    assert graph.edges == ()


def test_client_span_with_another_service_child_is_instrumented_not_inferred():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_gateway_payment_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    assert all(node.kind == "instrumented" for node in graph.nodes)
    assert {node.service_name for node in graph.nodes} == {"gateway", "payment"}


def test_topology_service_does_not_write_or_import_catalog():
    from apps.apm.services import topology as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "ApmService" not in source
    assert "DjangoTelemetryCatalogService" not in source
    assert "discover(" not in source


def test_inferred_mysql_node_exists_only_in_topology_result():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    assert {node.service_name for node in graph.nodes if node.kind == "inferred"} == {"mysql"}
    assert {node.service_name for node in graph.nodes if node.kind == "instrumented"} == {"gateway"}


def test_inferred_node_requires_org_visible_caller():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    assert graph.nodes == ()
    assert graph.edges == ()


def test_edge_sample_traces_include_both_caller_and_callee_identities():
    now = timezone.now()
    detail = _gateway_payment_trace(now)
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[detail]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    sample = graph.edges[0].sample_traces[0]
    assert sample.trace_id == detail.trace_id
    assert sample.caller_service_name == "gateway"
    span_ids = {span.span_id for span in detail.spans}
    assert sample.span_id in span_ids


def test_infer_downstream_fold_key_prefers_peer_service_then_system_then_address():
    assert infer_downstream({"peer.service": "orders-db", "db.system": "mysql"}).fold_key == "orders-db"
    assert infer_downstream({"db.system": "mysql"}).fold_key == "mysql"
    assert infer_downstream({"db.system.name": "redis"}).fold_key == "redis"
    assert infer_downstream({"messaging.system": "kafka"}).fold_key == "kafka"
    assert infer_downstream({"rpc.system": "grpc", "rpc.service": "billing.Invoice"}).fold_key == "billing.Invoice"
    assert infer_downstream({"server.address": "10.0.0.8"}).fold_key == "10.0.0.8"
    assert infer_downstream({"http.method": "GET"}) is None


def test_infer_downstream_keeps_host_port_and_db_name_separate():
    net_peer = infer_downstream({"db.system": "mysql", "net.peer.name": "db.internal", "net.peer.port": 3306})
    assert net_peer.fold_key == "mysql"
    assert net_peer.host == "db.internal"
    assert net_peer.port == "3306"
    assert net_peer.peer_address == "db.internal:3306"
    assert net_peer.db_name == ""

    server = infer_downstream({"db.system": "mysql", "server.address": "mysql.demo.svc", "server.port": "3306"})
    assert server.peer_address == "mysql.demo.svc:3306"
    assert infer_downstream({"db.system": "mysql", "network.peer.address": "10.1.1.1", "network.peer.port": 3306}).peer_address == "10.1.1.1:3306"
    assert infer_downstream({"db.system": "mysql", "net.peer.ip": "10.1.1.2"}).peer_address == "10.1.1.2"
    assert infer_downstream({"db.system": "mysql", "server.address": "mysql.svc", "net.peer.name": "other"}).host == "mysql.svc"

    host_only = infer_downstream({"db.system": "mysql", "server.address": "mysql.demo.svc", "db.name": "shop"})
    assert host_only.peer_address == "mysql.demo.svc"
    assert host_only.db_name == "shop"
    assert host_only.host != "shop"

    db_only = infer_downstream({"db.system": "mysql", "db.name": "shop"})
    assert db_only.peer_address == ""
    assert db_only.db_name == "shop"

    secret = infer_downstream(
        {
            "db.system": "mysql",
            "db.connection_string": "mysql://user:secret-pass@10.0.0.1:3306/shop",
            "db.query.text": "SELECT password FROM users",
        }
    )
    assert secret.peer_address == ""
    assert secret.host == ""
    assert "secret-pass" not in secret.peer_address
    assert format_peer_endpoint("::1", "3306") == "[::1]:3306"


def test_mysql_client_span_net_peer_name_and_port_surface_on_inferred_node():
    now = timezone.now()
    service = DjangoApmTopologyService(
        InMemoryTraceStore(details=[_mysql_client_trace(now, extra_attrs={"net.peer.name": "db.internal", "net.peer.port": 3306})])
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = next(node for node in graph.nodes if node.kind == "inferred")
    assert inferred.fold_key == "mysql"
    assert inferred.peer_address == "db.internal:3306"
    assert inferred.db_name == ""
    assert graph.edges[0].sample_traces[0].peer_address == "db.internal:3306"


def test_mysql_client_span_server_address_and_port_surface_on_inferred_node():
    now = timezone.now()
    service = DjangoApmTopologyService(
        InMemoryTraceStore(
            details=[_mysql_client_trace(now, extra_attrs={"server.address": "mysql.demo.svc", "server.port": "3306", "db.name": "shop"})]
        )
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = next(node for node in graph.nodes if node.kind == "inferred")
    assert inferred.peer_address == "mysql.demo.svc:3306"
    assert inferred.db_name == "shop"


def test_mysql_client_span_without_port_shows_host_only():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now, extra_attrs={"server.address": "mysql.demo.svc"})]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = next(node for node in graph.nodes if node.kind == "inferred")
    assert inferred.peer_address == "mysql.demo.svc"
    assert ":3306" not in inferred.peer_address


def test_db_name_does_not_become_peer_address_on_inferred_node():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now, extra_attrs={"db.name": "shop"})]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = next(node for node in graph.nodes if node.kind == "inferred")
    assert inferred.fold_key == "mysql"
    assert inferred.peer_address == ""
    assert inferred.db_name == "shop"


def test_two_mysql_hosts_fold_to_one_node_and_keep_unique_addresses():
    now = timezone.now()
    first = _mysql_client_trace(now, extra_attrs={"server.address": "10.0.0.1", "server.port": 3306, "db.name": "shop"})
    second = _mysql_client_trace(
        now,
        trace_id="c" * 32,
        extra_attrs={"server.address": "10.0.0.2", "server.port": 3306, "db.name": "shop"},
    )
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[first, second]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = [node for node in graph.nodes if node.kind == "inferred"]
    assert len(inferred) == 1
    assert inferred[0].fold_key == "mysql"
    assert set(inferred[0].peer_address.split(", ")) == {"10.0.0.1:3306", "10.0.0.2:3306"}
    assert inferred[0].db_name == "shop"
    sample_addresses = {item.peer_address for item in inferred[0].sample_traces}
    assert sample_addresses == {"10.0.0.1:3306", "10.0.0.2:3306"}


def test_span_attr_prefixed_net_peer_still_surfaces_host_port():
    now = timezone.now()
    service = DjangoApmTopologyService(
        InMemoryTraceStore(
            details=[
                _mysql_client_trace(
                    now,
                    extra_attrs={"span_attr:net.peer.name": "orders-db", "span_attr:network.peer.port": "3306"},
                )
            ]
        )
    )

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    inferred = next(node for node in graph.nodes if node.kind == "inferred")
    assert inferred.peer_address == "orders-db:3306"


def _user_entry_trace(now, *, trace_id="d" * 32, attrs=None, kind="server", parent=None, status="ok"):
    """根 Span 由外部请求触发的单服务 Trace；attrs/kind/parent 可调以覆盖判定边界。"""

    return _trace(
        trace_id,
        (
            _span(
                "6" * 16,
                parent,
                "GET /checkout",
                now,
                service="storefront",
                kind=kind,
                duration=30,
                status=status,
                attrs=attrs if attrs is not None else {"http.route": "/checkout"},
            ),
        ),
    )


def test_user_request_node_and_edge_appear_for_root_server_span_with_http_attrs():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_user_entry_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    node = next(node for node in graph.nodes if node.kind == "user_request")
    assert node.id == "user_request:prod"
    assert node.service_name == "user_request"
    assert node.health == "unknown"
    assert node.request_rate is None
    assert node.error_rate is None
    assert node.p95_ms is None
    edge = next(edge for edge in graph.edges if edge.source == "user_request:prod")
    assert edge.target == "shop:storefront:prod"
    assert edge.sampled_calls == 1
    assert edge.p95_ms == 30
    assert edge.error_rate == 0.0
    assert graph.data_state == "available"


def test_user_request_node_is_omitted_without_include_user_request_flag():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_user_entry_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_inferred=True,
    )

    assert all(node.kind != "user_request" for node in graph.nodes)
    assert all(not edge.source.startswith("user_request:") for edge in graph.edges)


def test_consumer_root_span_does_not_create_user_request_node():
    now = timezone.now()
    trace = _user_entry_trace(now, kind="consumer", attrs={"messaging.system": "kafka"})
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[trace]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    assert all(node.kind != "user_request" for node in graph.nodes)


def test_root_server_span_without_http_or_rpc_attrs_does_not_create_user_request_node():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_user_entry_trace(now, attrs={})]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    assert all(node.kind != "user_request" for node in graph.nodes)


def test_server_span_with_parent_outside_trace_still_counts_as_user_request_entry():
    now = timezone.now()
    trace = _user_entry_trace(now, parent="f" * 16, attrs={"span_attr:http.request.method": "GET"})
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[trace]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    assert any(node.kind == "user_request" for node in graph.nodes)


def test_rpc_system_root_server_span_counts_as_user_request_entry():
    now = timezone.now()
    trace = _user_entry_trace(now, attrs={"rpc.system": "grpc"})
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[trace]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    assert any(node.kind == "user_request" for node in graph.nodes)


def test_service_called_by_instrumented_upstream_gets_no_user_request_edge():
    now = timezone.now()
    trace = _trace(
        "b" * 32,
        (
            _span("1" * 16, None, "GET /checkout", now, service="gateway", attrs={"http.route": "/checkout"}),
            _span("2" * 16, "1" * 16, "POST /pay", now, service="gateway", kind="client", duration=20),
            _span("3" * 16, "2" * 16, "POST /pay", now, service="payment", duration=18, attrs={"http.route": "/pay"}),
        ),
    )
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[trace]))

    graph = service.build(
        [TopologyTarget("shop", "gateway", "prod"), TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    entry_edges = [edge for edge in graph.edges if edge.source.startswith("user_request:")]
    assert {edge.target for edge in entry_edges} == {"shop:gateway:prod"}


def test_user_request_entries_fold_into_one_node_per_environment():
    now = timezone.now()
    first = _user_entry_trace(now, trace_id="1" * 32)
    second = _user_entry_trace(now - timedelta(seconds=1), trace_id="2" * 32, status="error")
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[first, second]))

    graph = service.build(
        [TopologyTarget("shop", "storefront", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    nodes = [node for node in graph.nodes if node.kind == "user_request"]
    assert len(nodes) == 1
    edge = next(edge for edge in graph.edges if edge.source == "user_request:prod")
    assert edge.sampled_calls == 2
    assert edge.error_calls == 1
    assert edge.error_rate == 0.5


def test_user_request_node_is_omitted_when_entry_service_is_not_visible():
    now = timezone.now()
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_user_entry_trace(now)]))

    graph = service.build(
        [TopologyTarget("shop", "payment", "prod")],
        started_at=now - timedelta(hours=1),
        ended_at=now,
        include_user_request=True,
    )

    assert graph.nodes == ()
    assert graph.edges == ()


@pytest.mark.django_db
def test_topology_api_only_queries_targets_visible_to_current_organization(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now))
    catalog.discover(CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now))
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_gateway_payment_trace(now)]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 1
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}
    assert response.data["edges"][0]["p95_ms"] == 20


@pytest.mark.django_db
def test_topology_api_uses_service_visibility_instead_of_instance_visibility(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (20,))
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now))
    payment = catalog.discover(CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now))
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")
    catalog.set_service_organizations(payment.service.id, [10], actor="tester")
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_gateway_payment_trace(now)]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert {node["service_name"] for node in response.data["nodes"]} == {"gateway", "payment"}


@pytest.mark.django_db
def test_topology_api_does_not_leak_related_services_outside_service_scope(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (20,))
    catalog = DjangoTelemetryCatalogService()
    gateway = catalog.discover(CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now))
    catalog.discover(CatalogDiscovery("shop", "payment", "payment-1", "prod", seen_at=now))
    catalog.set_service_organizations(gateway.service.id, [10], actor="tester")
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_gateway_payment_trace(now)]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    response = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod"})

    assert response.status_code == 200
    assert response.data["sampled_traces"] == 0
    assert not response.data["nodes"]
    assert not response.data["edges"]


@pytest.mark.django_db
def test_topology_api_inferred_mysql_does_not_appear_in_service_catalog(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (10,))
    DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", "gateway", "gateway-1", "prod", seen_at=now))
    service = DjangoApmTopologyService(InMemoryTraceStore(details=[_mysql_client_trace(now)]))
    mocker.patch("apps.apm.views.topology.ApmTopologyViewSet._service", return_value=service)

    topology = apm_api_client.get("/api/v1/apm/topology/", {"environment": "prod", "include_inferred": True})
    catalog = apm_api_client.get("/api/v1/apm/services/")

    assert topology.status_code == 200
    assert {node["service_name"] for node in topology.data["nodes"] if node["kind"] == "inferred"} == {"mysql"}
    assert catalog.status_code == 200
    names = {item["name"] for item in catalog.data} if isinstance(catalog.data, list) else {item["name"] for item in catalog.data["items"]}
    assert "mysql" not in names
    assert not ApmService.objects.filter(name="mysql").exists()


def test_sample_traces_omitted_fetch_logs_template_without_leaking_payload(caplog):
    from apps.apm.adapters.victoriatraces import VictoriaTracesTelemetryStore

    class _Store(VictoriaTracesTelemetryStore):
        def __init__(self):
            super().__init__(endpoint="http://traces.test")

        def sample_traces(self, query: TopologySampleQuery):
            raise AssertionError("not used")

        def _query_rows(self, query, started_at, ended_at, *, limit=None):
            raise TelemetryStoreUnavailable("VictoriaTraces 查询不可用")

    store = _Store()
    caplog.set_level("WARNING", logger="apm")
    now = timezone.now()
    traces, omitted = store._fetch_topology_traces(
        ["secret-token-should-not-appear", "a" * 32],
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )

    assert traces == []
    assert omitted == 2
    records = [
        record
        for record in caplog.records
        if getattr(record, "msg", "") == "event=apm_topology_trace_fetch_failed failed_stage=sample_spans error_type=%s"
    ]
    assert records
    record: LogRecord = records[0]
    assert record.args == ("TelemetryStoreUnavailable",)
    rendered = record.getMessage()
    assert "TelemetryStoreUnavailable" in rendered
    assert "secret-token-should-not-appear" not in rendered
    assert "VictoriaTraces 查询不可用" not in rendered
