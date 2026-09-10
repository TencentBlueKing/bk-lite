import json
from datetime import timedelta
from logging import LogRecord
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone

from apps.apm.adapters import TelemetryQueryTooLarge, TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.adapters.victoriatraces import MAX_RESPONSE_BYTES, RESPONSE_TOO_LARGE, _pack_trace_ids
from apps.apm.services.contracts import (
    InstanceActivityQuery,
    MetricDataState,
    ServiceErrorBreakdownQuery,
    ServiceMetricQuery,
    SpanSearchQuery,
    SloMetricQuery,
    TopologyDependencyQuery,
    TopologySampleQuery,
    TraceSearchQuery,
)


def _span_row(trace_id, span_id, now, *, name="POST /checkout", service="checkout", parent="0" * 16, kind="2", status_code="2"):
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "name": name,
        "kind": kind,
        "status_code": status_code,
        "duration": "120000000",
        "start_time_unix_nano": str(int(now.timestamp() * 1_000_000_000)),
        "resource_attr:service.name": service,
        "resource_attr:service.namespace": "shop",
        "resource_attr:deployment.environment": "production",
        "resource_attr:service.instance.id": "pod-a",
    }


def _attr_row(trace_id, span_id, now, **extra):
    row = _span_row(trace_id, span_id, now)
    row.update(extra)
    return row


def _response(payload, status_code=200, *, raw=None):
    response = Mock()
    response.status_code = status_code
    response.headers = {}
    response.raise_for_status.return_value = None
    body = raw if raw is not None else json.dumps(payload).encode()
    response.iter_content.return_value = [body]
    return response


def _oversized_response():
    response = Mock()
    response.status_code = 200
    response.headers = {"Content-Length": str(MAX_RESPONSE_BYTES + 1)}
    response.raise_for_status.return_value = None
    response.iter_content.return_value = []
    return response


def test_search_builds_controlled_resource_filters_and_maps_logsql_spans():
    now = timezone.now()
    start_ns = str(int(now.timestamp() * 1_000_000_000))
    id_rows = json.dumps({"trace_id": "a" * 32, "matched_at": start_ns, "spans": 2})
    span_rows = "\n".join(
        [
            json.dumps(_span_row("a" * 32, "1" * 16, now, name="POST /checkout")),
            json.dumps(_span_row("a" * 32, "2" * 16, now, name="INSERT orders", parent="1" * 16, kind="3")),
        ]
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=id_rows.encode()),
        _response({}, raw=span_rows.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    page = store.search(
        TraceSearchQuery(
            started_at=now - timedelta(minutes=15),
            ended_at=now,
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
    query = session.get.call_args_list[0].kwargs["params"]["query"]
    assert '`resource_attr:service.name`:="checkout"' in query
    assert '`resource_attr:service.namespace`:="shop"' in query
    assert '`resource_attr:deployment.environment`:="production"' in query
    assert '`resource_attr:service.instance.id`:="pod-a"' in query
    assert "count() as spans" in query
    assert "/select/jaeger/api/traces" not in session.get.call_args_list[0].args[0]
    span_query = session.get.call_args_list[1].kwargs["params"]["query"]
    assert "| fields " in span_query
    assert "exception.stacktrace" not in span_query


def test_empty_trace_search_uses_bounded_trace_id_aggregation_and_cursor():
    now = timezone.now()
    start_ns = str(int(now.timestamp() * 1_000_000_000))
    older_ns = str(int((now - timedelta(seconds=1)).timestamp() * 1_000_000_000))
    id_rows = "\n".join(
        [
            json.dumps({"trace_id": "a" * 32, "matched_at": start_ns, "spans": 1}),
            json.dumps({"trace_id": "b" * 32, "matched_at": older_ns, "spans": 1}),
        ]
    )
    span_rows = "\n".join(
        [
            json.dumps(_span_row("a" * 32, "1" * 16, now, name="POST /checkout")),
            json.dumps(_span_row("b" * 32, "2" * 16, now - timedelta(seconds=1), name="POST /checkout")),
        ]
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=id_rows.encode()),
        _response({}, raw=span_rows.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)
    store.get_trace = Mock(wraps=store.get_trace)

    page = store.search(
        TraceSearchQuery(
            started_at=now - timedelta(minutes=15),
            ended_at=now,
            service_name=None,
            environment=None,
            limit=1,
        )
    )

    assert [item.trace_id for item in page.items] == ["a" * 32]
    assert page.next_cursor is not None
    store.get_trace.assert_not_called()
    params = session.get.call_args_list[0].kwargs["params"]
    assert "stats by (trace_id) max(start_time_unix_nano) as matched_at, count() as spans" in params["query"]
    assert "resource_attr:service.name" not in params["query"]
    assert "resource_attr:deployment.environment" not in params["query"]
    assert params["limit"] == 3
    span_path = session.get.call_args_list[1].args[0]
    assert span_path.endswith("/select/logsql/query")
    assert "/select/jaeger/api/traces/" not in span_path
    assert session.get.call_count == 2


def test_search_pages_newest_first_across_sample_slices_without_skipping_traces():
    """1h 窗口被切成 4 个 15m 切片；列表分页必须最新优先，且游标翻页不能漏掉任何 Trace。"""

    import re

    ended_at = timezone.now().replace(microsecond=0)
    started_at = ended_at - timedelta(hours=1)
    traces = {f"t{index:03d}".ljust(32, "0"): ended_at - timedelta(seconds=1 + index * 120) for index in range(30)}
    id_queries: list[tuple[str, object, object]] = []

    def fake_query_rows(logs_query, slice_started_at, slice_ended_at, limit=None):
        if "stats by (trace_id)" in logs_query:
            id_queries.append((logs_query, slice_started_at, slice_ended_at))
            vt_limit = int(re.search(r"\| limit (\d+)$", logs_query).group(1))
            rows = [
                {"trace_id": trace_id, "matched_at": str(int(matched_at.timestamp() * 1_000_000_000)), "spans": "1"}
                for trace_id, matched_at in traces.items()
                if slice_started_at <= matched_at < slice_ended_at
            ]
            rows.sort(key=lambda row: -int(row["matched_at"]))
            return rows[:vt_limit]
        requested = re.findall(r'"(t\d{3}0+)"', logs_query)
        return [
            _span_row(trace_id, f"s{trace_id[:15]}", traces[trace_id], service="datart")
            for trace_id in requested
            if slice_started_at <= traces[trace_id] < slice_ended_at
        ]

    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=Mock())
    store._query_rows = fake_query_rows

    paged: list[str] = []
    cursor = None
    first_page_id_queries = 0
    for page_no in range(10):
        page = store.search(
            TraceSearchQuery(
                started_at=started_at,
                ended_at=ended_at,
                service_name="datart",
                environment=None,
                limit=8,
                cursor=cursor,
            )
        )
        if page_no == 0:
            first_page_id_queries = len(id_queries)
        paged.extend(item.trace_id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    expected = sorted(traces, key=lambda trace_id: traces[trace_id], reverse=True)
    assert paged[:8] == expected[:8]
    assert paged == expected
    # 较新切片已凑够一页（8 + 8 > 9）时不再向更旧切片发 trace_id 查询：4 个切片只查了 2 个。
    assert first_page_id_queries == 2


def test_topology_sampling_keeps_round_robin_across_slices():
    ended_at = timezone.now().replace(microsecond=0)
    started_at = ended_at - timedelta(hours=1)
    candidates = (
        ("a" * 32, ended_at - timedelta(minutes=1)),
        ("b" * 32, ended_at - timedelta(minutes=2)),
        ("o" * 32, ended_at - timedelta(minutes=50)),
    )

    def fake_query_rows(logs_query, slice_started_at, slice_ended_at, limit=None):
        return [
            {"trace_id": trace_id, "matched_at": str(int(matched_at.timestamp() * 1_000_000_000)), "spans": "1"}
            for trace_id, matched_at in candidates
            if slice_started_at <= matched_at < slice_ended_at
        ]

    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=Mock())
    store._query_rows = fake_query_rows

    selected, _matched, _counts, truncated = store._sample_trace_ids(["*"], started_at=started_at, ended_at=ended_at, limit=2)
    newest_first, *_ = store._sample_trace_ids(["*"], started_at=started_at, ended_at=ended_at, limit=2, fill="newest_first")

    # 拓扑取样跨时段轮转：最新切片与最旧切片各取一条；列表分页则严格最新优先。
    assert selected == ["a" * 32, "o" * 32]
    assert truncated is True
    assert newest_first == ["a" * 32, "b" * 32]


def test_detail_preserves_waterfall_identity_for_server_side_authorization():
    now = timezone.now()
    structure = "\n".join(
        [
            json.dumps(_span_row("a" * 32, "1" * 16, now, name="POST /checkout")),
            json.dumps(_span_row("a" * 32, "2" * 16, now, name="INSERT orders", parent="1" * 16, kind="3")),
        ]
    )
    attributes = "\n".join(
        [
            json.dumps(
                _attr_row(
                    "a" * 32,
                    "1" * 16,
                    now,
                    **{
                        "span_attr:Authorization": "Bearer secret",
                        "event:event_attr:exception.type:0": "PaymentDeclinedError",
                        "event:event_attr:exception.message:0": "card declined",
                        "event:event_attr:exception.stacktrace:0": "at charge (payment.py:42)",
                    },
                )
            ),
            json.dumps(_attr_row("a" * 32, "2" * 16, now)),
        ]
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=structure.encode()),
        _response({}, raw=attributes.encode()),
    ]
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
    assert session.get.call_args_list[0].kwargs["params"]["query"].endswith(_trace_structure_suffix())
    assert "span_id:in(" in session.get.call_args_list[1].kwargs["params"]["query"]
    assert "/select/jaeger/api/traces/" not in session.get.call_args_list[0].args[0]


def _trace_structure_suffix():
    from apps.apm.adapters.victoriatraces import _trace_structure_fields_pipe

    return _trace_structure_fields_pipe()


def test_detail_deduplicates_replayed_spans_by_trace_and_span_identity():
    now = timezone.now()
    duplicated = "\n".join(
        [
            json.dumps(_span_row("a" * 32, "1" * 16, now)),
            json.dumps(_span_row("a" * 32, "1" * 16, now)),
            json.dumps(_span_row("a" * 32, "2" * 16, now, name="INSERT orders", parent="1" * 16, kind="3")),
        ]
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=duplicated.encode()),
        _response({}, raw=duplicated.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert len(detail.spans) == 2


def test_detail_maps_status_code_two_to_error_status():
    now = timezone.now()
    row = json.dumps(_span_row("a" * 32, "1" * 16, now, status_code="2"))
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=row.encode()),
        _response({}, raw=row.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.spans[0].status == "error"


def test_get_trace_reads_structure_then_span_attributes_via_logsql():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=json.dumps(_span_row("a" * 32, "1" * 16, now)).encode()),
        _response({}, raw=json.dumps(_attr_row("a" * 32, "1" * 16, now, **{"span_attr:http.route": "/checkout"})).encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.trace_id == "a" * 32
    assert detail.service_namespace == "shop"
    assert detail.service_name == "checkout"
    assert detail.instance_id == "pod-a"
    assert [span.name for span in detail.spans] == ["POST /checkout"]
    assert detail.spans[0].attributes["http.route"] == "/checkout"
    assert detail.spans[0].attributes["service.name"] == "checkout"
    assert not [key for key in detail.spans[0].attributes if key.startswith(("span_attr:", "resource_attr:"))]
    assert session.get.call_args_list[0].args[0].endswith("/select/logsql/query")
    assert session.get.call_args_list[1].args[0].endswith("/select/logsql/query")
    assert session.get.call_args_list[0].kwargs["params"]["query"].startswith(f'trace_id:={json.dumps("a" * 32)}')
    assert "span_id:in(" in session.get.call_args_list[1].kwargs["params"]["query"]


def test_get_trace_stays_missing_when_logsql_lacks_the_trace():
    session = Mock()
    session.get.return_value = _response({}, raw=b"")
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    assert store.get_trace("a" * 32) is None


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
    assert red.request_count == 6
    assert red.error_count == 2
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
    span_row = json.dumps(
        {
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
        }
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=id_row.encode()),
        _response({}, raw=span_row.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(minutes=15),
            ended_at=now,
            service_names=("gateway", 'pay"ment'),
            environment="prod",
            span_name="POST /checkout",
            status="error",
            limit=50,
        )
    )

    assert session.get.call_count == 2
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
    assert "count() as spans" in query
    assert "first 5000 by (_time desc)" not in query
    span_query = session.get.call_args_list[1].kwargs["params"]["query"]
    assert span_query.startswith('trace_id:in("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")')
    assert "| fields " in span_query
    assert "`span_attr:db.system`" in span_query
    assert "exception.stacktrace" not in span_query
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
    assert "| fields " in query
    assert session.get.call_args.kwargs["params"]["limit"] == 21


def test_search_spans_filters_entry_kinds_like_red_metrics():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response({}, raw=b"")
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    from apps.apm.services.contracts import SpanSearchQuery

    store.search_spans(
        SpanSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now,
            service_name="etl-worker",
            environment="production",
            status="error",
            kinds=("server", "consumer"),
            limit=20,
        )
    )

    query = session.get.call_args.kwargs["params"]["query"]
    assert 'kind:in("2","5")' in query
    assert 'status_code:="2"' in query
    assert 'kind:="' not in query


def _sample_id_row(trace_id, now):
    return json.dumps({"trace_id": trace_id, "matched_at": str(int(now.timestamp() * 1_000_000_000))})


def test_sample_traces_slices_one_hour_by_fifteen_minutes():
    now = timezone.now()
    trace_a, trace_b = "a" * 32, "b" * 32
    span_rows = "\n".join(
        json.dumps(_span_row(trace_id, span_id, now))
        for trace_id, span_id in ((trace_a, "1" * 16), (trace_b, "2" * 16))
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=_sample_id_row(trace_a, now).encode()),
        _response({}, raw=_sample_id_row(trace_b, now).encode()),
        _response({}, raw=b""),
        _response({}, raw=b""),
        _response({}, raw=span_rows.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now,
            service_names=("checkout",),
            limit=50,
        )
    )

    assert session.get.call_count == 5
    first_slice = session.get.call_args_list[0].kwargs["params"]
    assert first_slice["start"] == (now - timedelta(minutes=15)).isoformat()
    assert first_slice["end"] == now.isoformat()
    last_slice = session.get.call_args_list[3].kwargs["params"]
    assert last_slice["start"] == (now - timedelta(hours=1)).isoformat()
    assert last_slice["end"] == (now - timedelta(minutes=45)).isoformat()
    for call in session.get.call_args_list[:4]:
        query = call.kwargs["params"]["query"]
        assert "stats by (trace_id)" in query
        assert "count() as spans" in query
        assert "first 5000 by (_time desc)" not in query
    assert {trace.trace_id for trace in sample.traces} == {trace_a, trace_b}


def test_sample_traces_slices_one_day_by_hour():
    now = timezone.now()
    trace_a, trace_b = "a" * 32, "b" * 32
    span_rows = "\n".join(
        json.dumps(_span_row(trace_id, span_id, now))
        for trace_id, span_id in ((trace_a, "1" * 16), (trace_b, "2" * 16))
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=_sample_id_row(trace_a, now).encode()),
        *[_response({}, raw=b"") for _ in range(22)],
        _response({}, raw=_sample_id_row(trace_b, now).encode()),
        _response({}, raw=span_rows.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(days=1),
            ended_at=now,
            service_names=("checkout",),
            limit=50,
        )
    )

    assert session.get.call_count == 25
    first_slice = session.get.call_args_list[0].kwargs["params"]
    assert first_slice["start"] == (now - timedelta(hours=1)).isoformat()
    assert first_slice["end"] == now.isoformat()
    last_slice = session.get.call_args_list[23].kwargs["params"]
    assert last_slice["start"] == (now - timedelta(days=1)).isoformat()
    assert     last_slice["end"] == (now - timedelta(hours=23)).isoformat()
    for call in session.get.call_args_list[:24]:
        query = call.kwargs["params"]["query"]
        assert "stats by (trace_id)" in query
        assert "count() as spans" in query
        assert "first 5000 by (_time desc)" not in query
    assert {trace.trace_id for trace in sample.traces} == {trace_a, trace_b}


def test_sample_traces_slices_long_windows_and_round_robins_across_days():
    now = timezone.now()
    trace_a, trace_b = "a" * 32, "b" * 32
    span_rows = "\n".join(
        json.dumps(_span_row(trace_id, span_id, now))
        for trace_id, span_id in ((trace_a, "1" * 16), (trace_b, "2" * 16))
    )
    session = Mock()
    session.get.side_effect = [
        _response({}, raw=_sample_id_row(trace_a, now).encode()),
        _response({}, raw="\n".join([_sample_id_row(trace_b, now), _sample_id_row(trace_a, now)]).encode()),
        *[_response({}, raw=b"") for _ in range(5)],
        _response({}, raw=span_rows.encode()),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(days=7),
            ended_at=now,
            service_names=("checkout",),
            limit=50,
        )
    )

    assert session.get.call_count == 8
    first_slice = session.get.call_args_list[0].kwargs["params"]
    assert first_slice["start"] == (now - timedelta(days=1)).isoformat()
    assert first_slice["end"] == now.isoformat()
    last_slice = session.get.call_args_list[6].kwargs["params"]
    assert last_slice["start"] == (now - timedelta(days=7)).isoformat()
    assert last_slice["end"] == (now - timedelta(days=6)).isoformat()
    for call in session.get.call_args_list[:7]:
        query = call.kwargs["params"]["query"]
        assert "first 5000 by (_time desc)" in query
        assert "stats by (trace_id)" in query
        assert "count() as spans" in query
    span_query = session.get.call_args_list[7].kwargs["params"]["query"]
    assert f'trace_id:in("{trace_a}","{trace_b}")' in span_query
    assert "| fields " in span_query
    assert "exception.stacktrace" not in span_query
    assert {trace.trace_id for trace in sample.traces} == {trace_a, trace_b}
    assert sample.truncated is False


def test_oversized_topology_span_batch_splits_and_keeps_compact_traces(caplog):
    now = timezone.now()
    trace_ok, trace_fat = "a" * 32, "secret-token-should-not-appear"
    session = Mock()

    def get(url, **kwargs):
        query = str(kwargs.get("params", {}).get("query", ""))
        if "stats by (trace_id)" in query:
            return _response(
                {},
                raw="\n".join(
                    [_sample_id_row(trace_ok, now), _sample_id_row(trace_fat, now)]
                ).encode(),
            )
        if trace_ok in query and trace_fat in query:
            return _oversized_response()
        if trace_fat in query:
            return _oversized_response()
        return _response({}, raw=json.dumps(_span_row(trace_ok, "1" * 16, now)).encode())

    session.get.side_effect = get
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)
    caplog.set_level("WARNING", logger="apm")

    sample = store.sample_traces(
        TopologySampleQuery(
            started_at=now - timedelta(minutes=15),
            ended_at=now,
            service_names=("checkout",),
            limit=50,
        )
    )

    assert [trace.trace_id for trace in sample.traces] == [trace_ok]
    assert sample.omitted_trace_fetches == 1
    records = [
        record
        for record in caplog.records
        if getattr(record, "msg", "")
        == "event=apm_topology_trace_fetch_omitted failed_stage=sample_spans error_type=%s omitted_traces=%s"
    ]
    assert records
    record: LogRecord = records[0]
    assert record.args == ("TelemetryQueryTooLarge", 1)
    rendered = record.getMessage()
    assert "TelemetryQueryTooLarge" in rendered
    assert "omitted_traces=1" in rendered
    assert RESPONSE_TOO_LARGE not in rendered
    assert trace_fat not in rendered
    span_queries = [
        call.kwargs["params"]["query"]
        for call in session.get.call_args_list
        if "trace_id:in(" in call.kwargs["params"]["query"]
    ]
    assert any(trace_ok in query and trace_fat in query for query in span_queries)
    assert any(trace_ok in query and trace_fat not in query for query in span_queries)


def test_topology_span_fetch_still_unavailable_when_store_is_down():
    now = timezone.now()
    session = Mock()
    failed = Mock()
    failed.status_code = 500
    failed.headers = {}
    failed.raise_for_status.side_effect = requests.HTTPError("500", response=failed)
    session.get.side_effect = [
        _response({}, raw=_sample_id_row("a" * 32, now).encode()),
        failed,
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryStoreUnavailable, match="查询不可用"):
        store.sample_traces(
            TopologySampleQuery(
                started_at=now - timedelta(minutes=15),
                ended_at=now,
                service_names=("checkout",),
                limit=50,
            )
        )


def test_red_long_window_skips_trace_dedup_and_streams_aggregates():
    now = timezone.now()
    matrix = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"__name__": "requests"}, "values": [[1_785_888_000, "5"]]},
                {"metric": {"__name__": "errors"}, "values": [[1_785_888_000, "1"]]},
            ],
        },
    }
    endpoint_vector = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"__name__": "requests", "name": "POST /checkout"}, "value": [1_785_888_000, "6"]},
                {"metric": {"__name__": "errors", "name": "POST /checkout"}, "value": [1_785_888_000, "2"]},
                {"metric": {"__name__": "p95", "name": "POST /checkout"}, "value": [1_785_888_000, "100000000"]},
            ],
        },
    }
    session = Mock()
    session.get.side_effect = [
        _response(_vector(requests=6, errors=2, p95=100_000_000, p99=250_000_000)),
        _response(matrix),
        _response(endpoint_vector),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="prod",
            started_at=now - timedelta(days=7),
            ended_at=now,
            include_breakdown=True,
        )
    )

    assert session.get.call_count == 3
    for call in session.get.call_args_list:
        query = call.kwargs["params"]["query"]
        assert "stats by (trace_id" not in query
        assert 'kind:in("2","5")' in query
    endpoint_query = session.get.call_args_list[2].kwargs["params"]["query"]
    assert "stats by (name)" in endpoint_query
    assert red.request_rate == pytest.approx(6 / (7 * 86400))
    assert red.error_rate == pytest.approx(1 / 3)
    assert red.p95_ms == 100
    assert len(red.timeseries) == 1
    assert red.top_endpoints[0].endpoint == "POST /checkout"
    assert red.top_endpoints[0].error_rate == pytest.approx(1 / 3)


def test_red_short_window_keeps_exact_trace_span_dedup():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response(_vector(requests=6, errors=2, p95=100_000_000, p99=250_000_000))
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="prod",
            started_at=now - timedelta(days=1),
            ended_at=now,
        )
    )

    assert "stats by (trace_id, span_id)" in session.get.call_args.kwargs["params"]["query"]


def test_vt_client_side_rejection_maps_to_capacity_hint_not_unavailable():
    now = timezone.now()
    session = Mock()
    rejected = Mock()
    rejected.status_code = 422
    rejected.headers = {}
    rejected.raise_for_status.side_effect = requests.HTTPError("422 Unprocessable Entity", response=rejected)
    session.get.return_value = rejected
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryQueryTooLarge, match="超出单次查询容量"):
        store.service_red(ServiceMetricQuery("shop", "checkout", "prod", now - timedelta(minutes=1), now))


def _error_breakdown_session(*, red, endpoints, types, samples, recent):
    session = Mock()

    def get(url, **kwargs):
        query = str(kwargs.get("params", {}).get("query", ""))
        if url.endswith("/select/logsql/stats_query"):
            if "stats by (endpoint)" in query or "stats by (name)" in query:
                return _response(endpoints)
            return _response(red)
        if "stats by (kind" in query:
            return _ndjson(*types)
        if 'kind:in("2","5")' in query and "status_code:=\"2\"" in query:
            return _ndjson(*recent)
        return _ndjson(*samples)

    session.get.side_effect = get
    return session


def _ndjson(*rows):
    body = "\n".join(json.dumps(row) for row in rows)
    return _response({}, raw=body.encode())


def _grouped_vector(groups):
    result = []
    timestamp = 1_785_888_000
    for labels, values in groups:
        for name, value in values.items():
            result.append({"metric": {"__name__": name, **labels}, "value": [timestamp, str(value)]})
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def test_error_breakdown_coalesces_exception_over_error_type_and_merges_kinds():
    now = timezone.now()
    start_ns = str(int(now.timestamp() * 1_000_000_000))
    session = _error_breakdown_session(
        red=_vector(requests=10, errors=4, p95=100_000_000, p99=250_000_000),
        endpoints=_grouped_vector(
            [
                ({"endpoint": "POST /checkout"}, {"requests": 8, "errors": 3}),
                ({"endpoint": "GET /products"}, {"requests": 2, "errors": 1}),
            ]
        ),
        types=[
            {
                "c": "50",
                "kind": "3",
                "event:event_attr:exception.type:0": "",
                "span_attr:error.type": "payment_declined",
                "status_message": "payment_declined",
                "span_attr:http.response.status_code": "500",
                "last_seen": now.isoformat(),
            },
            {
                "c": "10",
                "kind": "2",
                "event:event_attr:exception.type:0": "",
                "span_attr:error.type": "payment_declined",
                "status_message": "payment_declined",
                "span_attr:http.response.status_code": "502",
                "last_seen": now.isoformat(),
            },
            {
                "c": "4",
                "kind": "2",
                "event:event_attr:exception.type:0": "BrokenPipeError",
                "span_attr:error.type": "server_error",
                "status_message": "server_error",
                "span_attr:http.response.status_code": "502",
                "event:event_attr:exception.message:0": "[Errno 32] Broken pipe",
                "last_seen": now.isoformat(),
            },
            {
                "c": "3",
                "kind": "3",
                "event:event_attr:exception.type:0": "",
                "span_attr:error.type": "",
                "status_message": "upstream timeout",
                "span_attr:http.response.status_code": "502",
                "last_seen": now.isoformat(),
            },
            {
                "c": "2",
                "kind": "1",
                "event:event_attr:exception.type:0": "",
                "span_attr:error.type": "",
                "status_message": "",
                "span_attr:http.response.status_code": "502",
                "last_seen": now.isoformat(),
            },
            {
                "c": "1",
                "kind": "1",
                "event:event_attr:exception.type:0": "",
                "span_attr:error.type": "",
                "status_message": "",
                "span_attr:http.response.status_code": "404",
                "last_seen": now.isoformat(),
            },
        ],
        samples=[_span_row("a" * 32, "1" * 16, now, name="POST /orders")],
        recent=[_span_row("b" * 32, "2" * 16, now, name="POST /checkout")],
    )
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)
    result = store.service_error_breakdown(
        ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(minutes=1), now, sample_limit=20)
    )

    assert result.request_count == 10
    assert result.error_count == 4
    assert result.failed_endpoints[0].endpoint == "POST /checkout"
    assert result.failed_endpoints[0].error_count == 3
    assert result.failed_endpoints[1].error_count == 1
    assert result.other_error_count == 0
    types = {item.error_type: item for item in result.error_types}
    assert types["payment_declined"].count == 60
    assert types["payment_declined"].location == "downstream"
    assert types["BrokenPipeError"].count == 4
    assert types["BrokenPipeError"].location == "entry"
    assert types["BrokenPipeError"].message == "[Errno 32] Broken pipe"
    assert types["upstream timeout"].count == 3
    assert types["upstream timeout"].location == "downstream"
    assert types["HTTP 502"].count == 2
    assert types["HTTP 502"].location == "internal"
    assert types["未携带错误信息"].count == 1
    assert result.recent_failures[0].trace_id == "b" * 32
    queries = [call.kwargs["params"]["query"] for call in session.get.call_args_list]
    assert any("stats by (endpoint)" in query and "kind:in(\"2\",\"5\")" in query for query in queries)
    assert any("`event:event_attr:exception.type:0`" in query and "`span_attr:error.type`" in query for query in queries)
    assert any("`event:event_attr:exception.message:0`" in query for query in queries if "stats by (kind" in query)
    assert any('shop' in query and "status_code:=\"2\"" in query and "kind:in" not in query.split("stats by")[0] for query in queries if "stats by (kind" in query)
    payment_query = next(query for query in queries if "payment_declined" in query and "sort by (_time)" in query)
    assert "not `event:event_attr:exception.type:0`:*" in payment_query
    assert "not `span_attr:error.type`:*" in payment_query
    http_query = next(query for query in queries if '`span_attr:http.response.status_code`:="502"' in query and "sort by (_time)" in query)
    assert "not `event:event_attr:exception.type:0`:*" in http_query
    assert "not status_message:*" in http_query
    unattributed_query = next(query for query in queries if ':~"^5"' in query and "sort by (_time)" in query)
    assert "not `span_attr:http.response.status_code`:~\"^5\"" in unattributed_query


def test_error_breakdown_failed_endpoints_remainder_matches_entry_error_count():
    now = timezone.now()
    session = _error_breakdown_session(
        red=_vector(requests=100, errors=40, p95=1, p99=2),
        endpoints=_grouped_vector(
            [
                ({"endpoint": "POST /a"}, {"requests": 50, "errors": 20}),
                ({"endpoint": "POST /b"}, {"requests": 30, "errors": 10}),
            ]
        ),
        types=[],
        samples=[],
        recent=[],
    )
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    result = store.service_error_breakdown(
        ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(minutes=1), now)
    )

    assert sum(item.error_count for item in result.failed_endpoints) + result.other_error_count == 40
    assert result.other_error_count == 10


def test_error_breakdown_escapes_service_filters_and_returns_no_data_without_entry_requests():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response(_vector())
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    empty = store.service_error_breakdown(
        ServiceErrorBreakdownQuery('shop" | stats count() as forged', "checkout", "prod", now - timedelta(minutes=1), now)
    )

    assert empty.data_state == MetricDataState.NO_DATA
    assert empty.failed_endpoints == ()
    query = session.get.call_args.kwargs["params"]["query"]
    assert 'shop\\" | stats count() as forged' in query


def test_error_breakdown_maps_upstream_failure_to_store_unavailable():
    now = timezone.now()
    session = Mock()
    failed = Mock()
    failed.status_code = 500
    failed.headers = {}
    failed.raise_for_status.side_effect = requests.HTTPError("500", response=failed)
    session.get.return_value = failed
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryStoreUnavailable, match="查询不可用"):
        store.service_error_breakdown(
            ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(minutes=1), now)
        )


def test_pack_trace_ids_uses_span_budget_and_falls_back_to_fixed_batches():
    packed = _pack_trace_ids([("a", 4000), ("b", 4000), ("c", 100)])
    assert packed == [["a"], ["b"], ["c"]]
    combined = _pack_trace_ids([("a", 2500), ("b", 2500), ("c", 100)])
    assert combined == [["a"], ["b", "c"]]
    fallback = _pack_trace_ids([("a", 0), ("b", 0), ("c", 0)], fallback_batch=2)
    assert fallback == [["a", "b"], ["c"]]


def test_slo_measurement_slices_windows_longer_than_one_day():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response(_vector(total=10, bad=2)),
        _response(_vector(total=5, bad=1)),
    ]
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)
    result = store.slo_measurement(
        SloMetricQuery("shop", "checkout", "prod", now - timedelta(days=2), now, "availability")
    )

    assert session.get.call_count == 2
    assert result.compliance_percent == pytest.approx(80)
    assert result.total_rate == pytest.approx(15 / (2 * 86400))
    first_end = session.get.call_args_list[0].kwargs["params"]["end"]
    second_start = session.get.call_args_list[1].kwargs["params"]["start"]
    assert first_end == second_start


def test_oversized_response_raises_query_too_large():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _oversized_response()
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryQueryTooLarge, match=RESPONSE_TOO_LARGE):
        store.search_spans(
            SpanSearchQuery(
                started_at=now - timedelta(minutes=15),
                ended_at=now,
                limit=20,
            )
        )
