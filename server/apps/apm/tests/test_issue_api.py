from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore
from apps.apm.services import DjangoTelemetryCatalogService, DjangoTelemetryIssueService, DjangoTelemetryQueryService
from apps.apm.services.contracts import CatalogDiscovery, IssueSearchQuery, SpanDetail, SpanPage, SpanSummary, TraceDetail
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _error_span(now, *, namespace="shop", instance_id="pod-a", trace_id="a" * 32, span_id="1" * 16):
    return SpanSummary(
        trace_id=trace_id,
        span_id=span_id,
        started_at=now,
        duration_ms=120,
        service_namespace=namespace,
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        status="error",
        name="POST /checkout",
        kind="server",
    )


def _trace(now, summary, *, message="card 424242 declined", version="v2"):
    span = SpanDetail(
        span_id=summary.span_id,
        parent_span_id=None,
        name=summary.name,
        started_at=now,
        duration_ms=summary.duration_ms,
        status="error",
        attributes={
            "exception.type": "PaymentDeclinedError",
            "exception.message": message,
            "exception.stacktrace": "PaymentDeclinedError: declined\n  at charge (payment.py:42)",
            "service.version": version,
        },
        service_namespace=summary.service_namespace,
        service_name=summary.service_name,
        environment=summary.environment,
        instance_id=summary.instance_id,
        kind="server",
    )
    return TraceDetail(
        trace_id=summary.trace_id,
        spans=(span,),
        service_namespace=summary.service_namespace,
        service_name=summary.service_name,
        environment=summary.environment,
        instance_id=summary.instance_id,
    )


def test_issue_service_clusters_real_exception_semantics_and_distributions():
    now = timezone.now()
    first = _error_span(now, trace_id="a" * 32, span_id="1" * 16)
    second = _error_span(now - timedelta(seconds=1), trace_id="b" * 32, span_id="2" * 16)
    store = InMemoryTraceStore(
        spans=(first, second),
        details=(
            _trace(now, first, message="card 424242 declined", version="v2"),
            _trace(now - timedelta(seconds=1), second, message="card 525252 declined", version="v3"),
        ),
    )
    query_service = DjangoTelemetryQueryService(trace_store=store)
    page = query_service.search_spans(IssueSearchQuery(now - timedelta(hours=1), now + timedelta(seconds=1), limit=50).span_query())

    result = DjangoTelemetryIssueService(query_service).project(page.items, next_cursor=None)

    assert len(result.items) == 1
    issue = result.items[0]
    assert issue.exception_type == "PaymentDeclinedError"
    assert issue.message == "card 424242 declined"
    assert issue.stacktrace.endswith("at charge (payment.py:42)")
    assert issue.occurrences == 2
    assert issue.affected_traces == 2
    assert [(item.value, item.count) for item in issue.version_distribution] == [("v2", 1), ("v3", 1)]
    assert [(item.value, item.count) for item in issue.endpoint_distribution] == [("POST /checkout", 2)]
    assert issue.fingerprint not in {"POST /checkout", first.trace_id, second.trace_id}


def test_issue_api_defaults_to_all_visible_services_and_keeps_cursor_bound(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (10,))
    create_application("hidden", (20,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "production", seen_at=now))
    catalog.discover(CatalogDiscovery("hidden", "checkout", "pod-hidden", "production", seen_at=now))
    allowed = _error_span(now)
    denied = _error_span(now, namespace="hidden", instance_id="pod-hidden", trace_id="b" * 32, span_id="2" * 16)
    query_service = mocker.Mock()
    query_service.search_spans.return_value = SpanPage((allowed, denied), "next-page")
    query_service.get_trace.side_effect = lambda trace_id: _trace(now, allowed) if trace_id == allowed.trace_id else _trace(now, denied)
    mocker.patch("apps.apm.views.issues.ApmIssueViewSet._query_service", return_value=query_service)

    response = apm_api_client.get("/api/v1/apm/issues/")

    assert response.status_code == 200
    called_query = query_service.search_spans.call_args.args[0]
    assert called_query.service_name is None
    assert called_query.environment is None
    assert called_query.status == "error"
    assert called_query.kind is None
    assert called_query.kinds is None
    assert called_query.limit == 50
    assert response.data["next_cursor"] == "next-page"
    assert response.data["truncated"] is True
    assert len(response.data["items"]) == 1
    assert response.data["items"][0]["service_namespace"] == "shop"


def test_issue_api_entry_only_scopes_to_server_and_consumer_error_spans(apm_api_client, mocker):
    now = timezone.now()
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "production", seen_at=now))
    query_service = mocker.Mock()
    query_service.search_spans.return_value = SpanPage((_error_span(now),), None)
    query_service.get_trace.return_value = _trace(now, _error_span(now))
    mocker.patch("apps.apm.views.issues.ApmIssueViewSet._query_service", return_value=query_service)

    response = apm_api_client.get(
        "/api/v1/apm/issues/",
        {
            "service_namespace": "shop",
            "service_name": "checkout",
            "environment": "production",
            "entry_only": True,
        },
    )

    assert response.status_code == 200
    called_query = query_service.search_spans.call_args.args[0]
    assert called_query.status == "error"
    assert called_query.kind is None
    assert called_query.kinds == ("server", "consumer")
    assert called_query.service_name == "checkout"
    assert called_query.environment == "production"


def test_issue_service_keeps_error_span_when_trace_detail_is_missing():
    now = timezone.now()
    summary = _error_span(now)
    store = InMemoryTraceStore(spans=(summary,))
    query_service = DjangoTelemetryQueryService(trace_store=store)
    page = query_service.search_spans(
        IssueSearchQuery(now - timedelta(hours=1), now + timedelta(seconds=1), limit=50).span_query()
    )

    result = DjangoTelemetryIssueService(query_service).project(page.items, next_cursor=None)

    assert len(result.items) == 1
    issue = result.items[0]
    assert issue.exception_type == "SpanError"
    assert issue.message == "OTel Span status=Error"
    assert issue.occurrences == 1
    assert issue.affected_traces == 1
    assert issue.sample_traces[0].trace_id == summary.trace_id


@pytest.mark.parametrize("params", [{"limit": 101}, {"status": "ok"}, {"started_at": "bad"}])
def test_issue_api_rejects_unbounded_or_client_controlled_error_queries(apm_api_client, params):
    response = apm_api_client.get("/api/v1/apm/issues/", params)

    assert response.status_code == 400
