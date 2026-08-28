import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.services.contracts import (
    InstanceActivityQuery,
    MetricDataState,
    ServiceMetricQuery,
    SloMetricQuery,
    TopologyDependencyQuery,
    TopologySampleQuery,
    TraceSearchQuery,
)


def _response(payload, status_code=200, *, raw=None):
    response = Mock()
    response.status_code = status_code
    response.headers = {}
    response.raise_for_status.return_value = None
    body = raw if raw is not None else json.dumps(payload).encode()
    response.iter_content.return_value = [body]
    return response


def _jaeger_trace(now):
    start_us = int(now.timestamp() * 1_000_000)
    return {
        "traceID": "a" * 32,
        "processes": {
            "p1": {
                "serviceName": "checkout",
                "tags": [
                    {"key": "service.namespace", "value": "shop"},
                    {"key": "service.instance.id", "value": "pod-a"},
                    {"key": "deployment.environment", "value": "production"},
                ],
            }
        },
        "spans": [
            {
                "spanID": "1" * 16,
                "operationName": "POST /checkout",
                "processID": "p1",
                "startTime": start_us,
                "duration": 120_000,
                "references": [],
                "tags": [
                    {"key": "span.kind", "value": "server"},
                    {"key": "otel.status_code", "value": "ERROR"},
                    {"key": "Authorization", "value": "Bearer secret"},
                ],
            },
            {
                "spanID": "2" * 16,
                "operationName": "INSERT orders",
                "processID": "p1",
                "startTime": start_us + 10_000,
                "duration": 20_000,
                "references": [{"refType": "CHILD_OF", "spanID": "1" * 16}],
                "tags": [{"key": "span.kind", "value": "client"}],
            },
        ],
    }


def test_search_builds_controlled_resource_filters_and_maps_jaeger_trace():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response({"data": [_jaeger_trace(now)]})
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    page = store.search(
        TraceSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(minutes=1),
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            instance_id="pod-a",
            limit=20,
        )
    )

    assert len(page.items) == 1
    summary = page.items[0]
    assert summary.trace_id == "a" * 32
    assert summary.root_span_name == "POST /checkout"
    assert summary.status == "error"
    assert summary.span_count == 2
    params = session.get.call_args.kwargs["params"]
    assert params["service"] == "checkout"
    assert params["limit"] == 21
    assert json.loads(params["tags"]) == {
        "resource_attr:deployment.environment": "production",
        "resource_attr:service.namespace": "shop",
        "resource_attr:service.instance.id": "pod-a",
    }


def test_empty_trace_search_uses_bounded_trace_id_aggregation_and_cursor():
    now = timezone.now()
    first = _jaeger_trace(now)
    second = _jaeger_trace(now - timedelta(seconds=1))
    second["traceID"] = "b" * 32
    rows = "\n".join(
        json.dumps({"trace_id": trace_id, "matched_at": str(int(at.timestamp() * 1_000_000_000))})
        for trace_id, at in (("a" * 32, now), ("b" * 32, now - timedelta(seconds=1)))
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=rows.encode()),
        _response({"data": [first]}),
        _response({"data": [second]}),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    page = store.search(
        TraceSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(minutes=1),
            service_name=None,
            environment=None,
            limit=1,
        )
    )

    assert [item.trace_id for item in page.items] == ["a" * 32]
    assert page.next_cursor is not None
    params = session.get.call_args_list[0].kwargs["params"]
    assert "stats by (trace_id) max(start_time_unix_nano) as matched_at" in params["query"]
    assert "resource_attr:service.name" not in params["query"]
    assert "resource_attr:deployment.environment" not in params["query"]
    assert params["limit"] == 2


def test_detail_preserves_waterfall_identity_for_server_side_authorization():
    now = timezone.now()
    raw_trace = _jaeger_trace(now)
    raw_trace["spans"][0]["logs"] = [
        {
            "fields": [
                {"key": "event", "value": "exception"},
                {"key": "exception.type", "value": "PaymentDeclinedError"},
                {"key": "exception.message", "value": "card declined"},
                {"key": "exception.stacktrace", "value": "at charge (payment.py:42)"},
            ]
        }
    ]
    session = Mock()
    session.get.return_value = _response({"data": [raw_trace]})
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.instance_id == "pod-a"
    assert detail.spans[1].parent_span_id == "1" * 16
    assert detail.spans[0].kind == "server"
    assert detail.spans[0].attributes["Authorization"] == "Bearer secret"
    assert detail.spans[0].attributes["event_attr:exception.type"] == "PaymentDeclinedError"
    assert detail.spans[0].attributes["event_attr:exception.message"] == "card declined"
    assert detail.spans[0].attributes["event_attr:exception.stacktrace"] == "at charge (payment.py:42)"


def test_detail_deduplicates_replayed_spans_by_trace_and_span_identity():
    now = timezone.now()
    raw_trace = _jaeger_trace(now)
    raw_trace["spans"].append(dict(raw_trace["spans"][0]))
    session = Mock()
    session.get.return_value = _response({"data": [raw_trace]})
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert len(detail.spans) == 2


def test_detail_maps_victoriatraces_string_error_tag_to_error_status():
    now = timezone.now()
    raw_trace = _jaeger_trace(now)
    raw_trace["spans"][0]["tags"] = [
        {"key": "span.kind", "value": "server"},
        {"key": "error", "type": "string", "value": "true"},
    ]
    session = Mock()
    session.get.return_value = _response({"data": [raw_trace]})
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.spans[0].status == "error"


def test_transport_failures_are_mapped_to_trace_store_degradation():
    session = Mock()
    session.get.side_effect = requests.Timeout("down")
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryStoreUnavailable, match="查询不可用"):
        store.get_trace("a" * 32)


def test_store_reads_victoria_traces_host(monkeypatch):
    monkeypatch.delenv("APM_VICTORIATRACES_QUERY_ENDPOINT", raising=False)
    monkeypatch.setenv("VICTORIATRACES_HOST", "http://victoria-traces:10428")

    store = VictoriaTracesTelemetryStore()

    assert store.endpoint == "http://victoria-traces:10428"


def test_store_prefers_victoria_traces_host_over_legacy_query_endpoint(monkeypatch):
    monkeypatch.setenv("VICTORIATRACES_HOST", "http://victoria-traces:10428")
    monkeypatch.setenv("APM_VICTORIATRACES_QUERY_ENDPOINT", "http://127.0.0.1:10428")

    store = VictoriaTracesTelemetryStore()

    assert store.endpoint == "http://victoria-traces:10428"


def _vector(**values):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"__name__": name}, "value": [1_785_888_000, str(value)]} for name, value in values.items()],
        },
    }


def test_red_uses_deduplicated_trace_span_aggregation_and_escapes_filters():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response(_vector(requests=6, errors=2, p95=100_000_000, p99=250_000_000))
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace='shop" | stats count() as forged',
            service_name="checkout",
            environment="prod",
            started_at=now - timedelta(seconds=60),
            ended_at=now,
        )
    )

    assert red.request_rate == pytest.approx(0.1)
    assert red.error_rate == pytest.approx(1 / 3)
    assert red.p95_ms == 100
    assert red.p99_ms == 250
    params = session.get.call_args.kwargs["params"]
    assert "stats by (trace_id, span_id)" in params["query"]
    assert 'shop\\" | stats count() as forged' in params["query"]
    assert session.get.call_args.kwargs["stream"] is True


def test_red_scopes_every_aggregate_to_the_selected_endpoint():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response(_vector(requests=6, errors=2, p95=100_000_000, p99=250_000_000))
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="prod",
            started_at=now - timedelta(seconds=60),
            ended_at=now,
            endpoint='POST /checkout" | stats count() as forged',
            version='v2" | stats count() as forged',
        )
    )

    query = session.get.call_args.kwargs["params"]["query"]
    assert 'name:="POST /checkout\\" | stats count() as forged"' in query
    assert '`resource_attr:service.version`:="v2\\" | stats count() as forged"' in query


def test_slo_uses_deduplicated_counts_and_preserves_no_data_semantics():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response(_vector(total=10, bad=2)),
        _response(_vector()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)
    query = SloMetricQuery("shop", "checkout", "prod", now - timedelta(seconds=100), now, "availability")

    available = store.slo_measurement(query)
    no_data = store.slo_measurement(query)

    assert available.compliance_percent == 80
    assert available.good_rate == pytest.approx(0.08)
    assert available.total_rate == pytest.approx(0.1)
    assert available.data_state == MetricDataState.AVAILABLE
    assert no_data.data_state == MetricDataState.NO_DATA
    assert no_data.compliance_percent is None


def test_activity_and_dependencies_are_mapped_from_bounded_vt_endpoints():
    now = timezone.now()
    activity = {
        "last_seen": str(int(now.timestamp() * 1_000_000_000)),
        "resource_attr:service.namespace": "shop",
        "resource_attr:service.name": "checkout",
        "resource_attr:service.instance.id": "pod-a",
        "resource_attr:deployment.environment": "prod",
        "resource_attr:service.version": "1.2.3",
    }
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=json.dumps(activity).encode()),
        _response({"data": [{"parent": "gateway", "child": "checkout", "callCount": 12}]}),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    activities = store.instance_activity(InstanceActivityQuery(now - timedelta(hours=1), now))
    dependencies = store.service_dependencies(TopologyDependencyQuery(now - timedelta(hours=1), now))

    assert activities[0].service_namespace == "shop"
    assert activities[0].instance_id == "pod-a"
    assert activities[0].version == "1.2.3"
    assert dependencies[0].call_count == 12
    dependency_call = session.get.call_args_list[1]
    assert dependency_call.args[0].endswith("/select/jaeger/api/dependencies")
    assert dependency_call.kwargs["params"]["lookback"] == 3_600_000


def test_sample_traces_uses_templated_logsql_and_fetches_trace_details():
    now = timezone.now()
    start_ns = str(int(now.timestamp() * 1_000_000_000))
    id_row = json.dumps({"trace_id": "a" * 32, "matched_at": start_ns})
    span_row = json.dumps({
        "trace_id": "a" * 32,
        "span_id": "1" * 16,
        "parent_span_id": "0" * 16,
        "name": "POST /checkout",
        "kind": "2",
        "status_code": "2",
        "duration": "120000000",
        "start_time_unix_nano": start_ns,
        "resource_attr:service.name": "checkout",
        "resource_attr:service.namespace": "shop",
        "resource_attr:deployment.environment": "prod",
        "span_attr:http.route": "/checkout",
        "span_attr:db.system": "mysql",
    })
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=id_row.encode()),
        _response({}, raw=span_row.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now,
            service_names=("gateway", 'pay"ment'),
            environment="prod",
            span_name="POST /checkout",
            status="error",
            limit=50,
        )
    )

    assert len(sample.traces) == 1
    assert sample.traces[0].trace_id == "a" * 32
    assert sample.traces[0].spans[0].kind == "server"
    assert sample.traces[0].spans[0].parent_span_id is None
    assert sample.traces[0].spans[0].attributes["span_attr:db.system"] == "mysql"
    assert sample.truncated is False
    query = session.get.call_args_list[0].kwargs["params"]["query"]
    assert '`resource_attr:service.name`:in("gateway","pay\\"ment")' in query
    assert '`resource_attr:deployment.environment`:="prod"' in query
    assert 'name:="POST /checkout"' in query
    assert 'status_code:="2"' in query
    span_query = session.get.call_args_list[1].kwargs["params"]["query"]
    assert span_query.startswith('trace_id:in("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")')
    assert session.get.call_args_list[1].args[0].endswith("/select/logsql/query")
    assert "/select/jaeger/api/traces/" not in session.get.call_args_list[1].args[0]


def test_all_stats_queries_are_time_bounded_to_vt_retention_contract():
    now = timezone.now()
    session = Mock()
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(ValueError, match="35 天"):
        store.service_red(ServiceMetricQuery("shop", "checkout", "prod", now - timedelta(days=36), now))

    session.get.assert_not_called()


def test_unique_span_limit_rejects_instead_of_silently_undercounting(monkeypatch):
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response(_vector(requests=2, errors=0, p95=10, p99=10)),
        _response(_vector(unique_spans=3)),
    ]
    monkeypatch.setattr("apps.apm.adapters.victoriatraces.MAX_UNIQUE_SPANS", 2)
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryStoreUnavailable, match="唯一 Span 数"):
        store.service_red(ServiceMetricQuery("shop", "checkout", "prod", now - timedelta(minutes=1), now))

    assert "| limit 2 | stats" in session.get.call_args_list[0].kwargs["params"]["query"]
    assert "| limit 3 | stats count() as unique_spans" in session.get.call_args_list[1].kwargs["params"]["query"]


def test_search_spans_builds_controlled_logsql_and_maps_rows():
    now = timezone.now()
    start_ns = int(now.timestamp() * 1_000_000_000)
    row = {
        "trace_id": "a" * 32,
        "span_id": "1" * 16,
        "name": "GET /lab/health",
        "kind": "2",
        "status_code": "1",
        "duration": "12000000",
        "start_time_unix_nano": str(start_ns),
        "resource_attr:service.namespace": "lab149",
        "resource_attr:service.name": "weops-lite-probe",
        "resource_attr:deployment.environment": "lab",
        "resource_attr:service.instance.id": "10.10.41.149",
        "span_attr:http.request.method": "GET",
        "span_attr:http.response.status_code": "200",
    }
    session = Mock()
    session.get.return_value = _response({}, raw=(json.dumps(row) + "\n").encode())
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    from apps.apm.services.contracts import SpanSearchQuery

    page = store.search_spans(
        SpanSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(minutes=1),
            service_namespace="lab149",
            service_name="weops-lite-probe",
            environment="lab",
            instance_id="10.10.41.149",
            span_name='GET /lab/health"evil',
            status="ok",
            kind="server",
            min_duration_ms=1,
            max_duration_ms=50,
            limit=20,
        )
    )

    assert len(page.items) == 1
    item = page.items[0]
    assert item.span_id == "1" * 16
    assert item.name == "GET /lab/health"
    assert item.kind == "server"
    assert item.status == "ok"
    assert item.http_method == "GET"
    assert item.http_status_code == "200"
    assert abs(item.duration_ms - 12.0) < 0.001
    query = session.get.call_args.kwargs["params"]["query"]
    assert '`resource_attr:service.name`:="weops-lite-probe"' in query
    assert 'name:="GET /lab/health\\"evil"' in query
    assert 'status_code:="1"' in query
    assert 'kind:="2"' in query
    assert "duration:>=1000000" in query
    assert "duration:<=50000000" in query
    assert session.get.call_args.kwargs["params"]["limit"] == 21
