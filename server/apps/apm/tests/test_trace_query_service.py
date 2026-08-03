from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore
from apps.apm.services import DjangoTelemetryQueryService
from apps.apm.services.contracts import SpanDetail, TraceDetail
from apps.apm.services.trace_sanitizer import MAX_ATTRIBUTE_VALUE_LENGTH, MAX_TRACE_SPANS


def test_trace_detail_drops_sensitive_internal_and_body_attributes_and_bounds_values():
    now = timezone.now()
    span = SpanDetail(
        span_id="span-a",
        parent_span_id=None,
        name="POST /checkout",
        started_at=now,
        duration_ms=12,
        status="error",
        attributes={
            "http.route": "/checkout",
            "Authorization": "Bearer secret",
            "http.request.header.cookie": "session=secret",
            "db.password": "secret",
            "api_key": "secret",
            "http.request.body": "card=secret",
            "url.full": "https://example.com/orders/12345?token=secret",
            "url.path": "/orders/12345",
            "url.query": "token=secret",
            "url.fragment": "private-section",
            "http.url": "https://example.com/orders/12345?token=secret",
            "http.target": "/orders/12345?token=secret",
            "bk.ingest_source.id": str(uuid4()),
            "bk.apm.original_span_name": "GET /orders/12345?token=secret",
            "request.headers": {"Authorization": "Bearer nested", "x-request-id": "safe"},
            "exception.message": "x" * (MAX_ATTRIBUTE_VALUE_LENGTH + 50),
        },
    )
    detail = TraceDetail("a" * 32, (span,), "shop", "checkout", "prod", "pod-a")
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[detail]))

    result = service.get_trace(detail.trace_id)

    assert result is not None
    assert result.spans[0].attributes == {
        "http.route": "/checkout",
        "request.headers": {"x-request-id": "safe"},
        "exception.message": "x" * MAX_ATTRIBUTE_VALUE_LENGTH,
    }
    assert result.truncated is True


def test_trace_detail_caps_span_count_and_marks_partial_response():
    now = timezone.now()
    spans = tuple(SpanDetail(str(index), None, "work", now + timedelta(microseconds=index), 1, "ok") for index in range(MAX_TRACE_SPANS + 1))
    detail = TraceDetail("b" * 32, spans, "shop", "checkout", "prod", "pod-a")
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[detail]))

    result = service.get_trace(detail.trace_id)

    assert result is not None
    assert len(result.spans) == MAX_TRACE_SPANS
    assert result.truncated is True
