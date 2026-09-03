from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore, InMemoryTraceStore
from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    MetricDataState,
    ServiceErrorBreakdownQuery,
    ServiceMetricQuery,
    ServiceRed,
    SpanSummary,
    TraceDetail,
    TraceSearchQuery,
    TraceSummary,
)


def test_trace_store_filters_and_pages_without_external_query_language():
    now = timezone.now()
    summaries = [
        TraceSummary(
            trace_id=f"trace-{index}",
            started_at=now - timedelta(minutes=index),
            duration_ms=10,
            service_namespace="shop",
            service_name="checkout",
            environment="prod",
            instance_id=f"pod-{index}",
            status="ok",
        )
        for index in range(3)
    ]
    store = InMemoryTraceStore(summaries=summaries)
    query = TraceSearchQuery(
        started_at=now - timedelta(hours=1),
        ended_at=now,
        service_namespace="shop",
        service_name="checkout",
        environment="prod",
        limit=2,
    )

    first = store.search(query)
    second = store.search(TraceSearchQuery(**{**query.__dict__, "cursor": first.next_cursor}))

    assert [item.trace_id for item in first.items] == ["trace-0", "trace-1"]
    assert [item.trace_id for item in second.items] == ["trace-2"]
    assert second.next_cursor is None


def test_metric_store_supports_exact_red_and_bounded_activity_queries():
    now = timezone.now()
    metric_query = ServiceMetricQuery("shop", "checkout", "prod", now - timedelta(hours=1), now)
    red = ServiceRed(request_rate=12, error_rate=0.1, p95_ms=80, p99_ms=120)
    activity = InstanceActivity("shop", "checkout", "pod-a", "prod", "1.0", now)
    store = InMemoryMetricStore(service_metrics=[(metric_query, red)], activities=[activity])

    assert store.service_red(metric_query) == red
    assert store.instance_activity(
        InstanceActivityQuery(
            started_at=now - timedelta(minutes=5),
            ended_at=now + timedelta(minutes=1),
        )
    ) == [activity]


def _span(now, *, span_id, name, kind, status="ok", **extra):
    return SpanSummary(
        trace_id=span_id.replace("s", "t")[:32].ljust(32, "0"),
        span_id=span_id.ljust(16, "0"),
        started_at=now,
        duration_ms=20,
        service_namespace="shop",
        service_name="checkout",
        environment="prod",
        instance_id="pod-a",
        status=status,
        name=name,
        kind=kind,
        **extra,
    )


def test_memory_store_error_breakdown_counts_entry_failures_and_attributes_all_error_spans():
    now = timezone.now()
    spans = [
        _span(now - timedelta(seconds=9), span_id="ok1", name="POST /checkout", kind="server"),
        _span(now - timedelta(seconds=8), span_id="ok2", name="POST /checkout", kind="server"),
        _span(
            now - timedelta(seconds=7),
            span_id="e1",
            name="POST /checkout",
            kind="server",
            status="error",
            span_error_type="server_error",
            status_message="server_error",
            http_status_code="502",
        ),
        _span(
            now - timedelta(seconds=6),
            span_id="e2",
            name="POST /checkout",
            kind="server",
            status="error",
            span_error_type="server_error",
            status_message="server_error",
            http_status_code="502",
        ),
        _span(
            now - timedelta(seconds=5),
            span_id="e3",
            name="GET /products",
            kind="server",
            status="error",
            span_error_type="server_error",
            status_message="server_error",
            http_status_code="500",
        ),
        _span(
            now - timedelta(seconds=4),
            span_id="c1",
            name="POST /orders",
            kind="client",
            status="error",
            span_error_type="payment_declined",
            status_message="payment_declined",
        ),
        _span(
            now - timedelta(seconds=3),
            span_id="c2",
            name="POST /orders",
            kind="client",
            status="error",
            span_error_type="payment_declined",
            status_message="payment_declined",
        ),
        _span(
            now - timedelta(seconds=2),
            span_id="c3",
            name="GET /products",
            kind="client",
            status="error",
            span_error_type="downstream_error",
            status_message="downstream_error",
        ),
        _span(
            now - timedelta(seconds=1),
            span_id="ex1",
            name="POST /checkout",
            kind="server",
            status="error",
            exception_type="BrokenPipeError",
            exception_message="[Errno 32] Broken pipe",
            span_error_type="server_error",
            status_message="BrokenPipeError: [Errno 32] Broken pipe",
            http_status_code="502",
        ),
    ]
    store = InMemoryTraceStore(spans=spans)
    query = ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(hours=1), now, sample_limit=20)

    result = store.service_error_breakdown(query)

    assert result.data_state == MetricDataState.AVAILABLE
    assert result.request_count == 6
    assert result.error_count == 4
    assert result.error_rate == pytest.approx(4 / 6)
    assert [item.endpoint for item in result.failed_endpoints] == ["POST /checkout", "GET /products"]
    assert result.failed_endpoints[0].error_count == 3
    assert result.failed_endpoints[0].request_count == 5
    assert result.failed_endpoints[1].error_count == 1
    assert result.other_error_count == 0
    types = {item.error_type: item for item in result.error_types}
    assert types["payment_declined"].count == 2
    assert types["payment_declined"].location == "downstream"
    assert types["server_error"].count == 3
    assert types["server_error"].location == "entry"
    assert types["downstream_error"].count == 1
    assert types["BrokenPipeError"].count == 1
    assert types["BrokenPipeError"].location == "entry"
    assert types["BrokenPipeError"].message == "[Errno 32] Broken pipe"
    assert "SpanError" not in types
    assert result.recent_failures[0].span_id.startswith("ex1")
    assert all(item.kind == "server" for item in result.recent_failures)


def test_memory_store_error_breakdown_returns_no_data_without_entry_spans():
    now = timezone.now()
    store = InMemoryTraceStore(
        spans=(
            _span(
                now,
                span_id="c1",
                name="POST /orders",
                kind="client",
                status="error",
                span_error_type="payment_declined",
            ),
        )
    )

    result = store.service_error_breakdown(
        ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(hours=1), now)
    )

    assert result.data_state == MetricDataState.NO_DATA
    assert result.request_count is None
    assert result.error_types == ()
    assert result.recent_failures == ()


def test_memory_store_error_breakdown_prefers_status_message_over_http_then_unattributed():
    now = timezone.now()
    store = InMemoryTraceStore(
        spans=(
            _span(now - timedelta(seconds=3), span_id="ok1", name="GET /health", kind="server"),
            _span(
                now - timedelta(seconds=2),
                span_id="e1",
                name="GET /health",
                kind="server",
                status="error",
                status_message="upstream timeout",
                http_status_code="502",
            ),
            _span(
                now - timedelta(seconds=1),
                span_id="e2",
                name="GET /health",
                kind="internal",
                status="error",
                http_status_code="404",
            ),
        )
    )

    result = store.service_error_breakdown(
        ServiceErrorBreakdownQuery("shop", "checkout", "prod", now - timedelta(hours=1), now)
    )

    types = {item.error_type: item for item in result.error_types}
    assert types["upstream timeout"].count == 1
    assert "HTTP 502" not in types
    assert types["未携带错误信息"].count == 1
