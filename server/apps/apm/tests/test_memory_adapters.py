from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore, InMemoryTraceStore
from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    ServiceMetricQuery,
    ServiceRed,
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
