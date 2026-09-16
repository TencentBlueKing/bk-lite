import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, VictoriaTracesTelemetryStore
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
    span_details = {
        (allowed.trace_id, allowed.span_id): _trace(now, allowed).spans[0],
        (denied.trace_id, denied.span_id): _trace(now, denied).spans[0],
    }
    query_service.get_span_details.side_effect = lambda keys: {key: span_details[key] for key in keys if key in span_details}
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
    summary = _error_span(now)
    query_service.search_spans.return_value = SpanPage((summary,), None)
    query_service.get_span_details.return_value = {(summary.trace_id, summary.span_id): _trace(now, summary).spans[0]}
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


class _CountingTraceStore:
    def __init__(self, inner):
        self._inner = inner
        self.get_trace_calls = 0
        self.get_span_details_calls = 0

    def get_trace(self, trace_id):
        self.get_trace_calls += 1
        return self._inner.get_trace(trace_id)

    def get_span_details(self, keys):
        self.get_span_details_calls += 1
        return self._inner.get_span_details(keys)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _vt_response(raw: str):
    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.raise_for_status.return_value = None
    response.iter_content.return_value = [raw.encode()]
    return response


def _vt_span_row(trace_id, span_id, now):
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": "0" * 16,
        "name": "POST /checkout",
        "kind": "2",
        "status_code": "2",
        "duration": "120000000",
        "start_time_unix_nano": str(int(now.timestamp() * 1_000_000_000)),
        "resource_attr:service.name": "checkout",
        "resource_attr:service.namespace": "shop",
        "resource_attr:deployment.environment": "production",
        "resource_attr:service.instance.id": "pod-a",
    }


def test_issue_service_loads_fifty_error_traces_without_per_trace_get_trace():
    now = timezone.now()
    summaries = tuple(
        _error_span(now - timedelta(seconds=index), trace_id=f"{index:032x}", span_id=f"{index:016x}")
        for index in range(50)
    )
    store = _CountingTraceStore(
        InMemoryTraceStore(
            spans=summaries,
            details=tuple(_trace(summary.started_at, summary) for summary in summaries),
        )
    )
    query_service = DjangoTelemetryQueryService(trace_store=store)

    result = DjangoTelemetryIssueService(query_service).project(summaries, next_cursor=None)

    assert store.get_trace_calls == 0
    assert store.get_span_details_calls == 1
    assert len(result.items) == 1
    assert result.items[0].occurrences == 50
    assert result.items[0].affected_traces == 50
    assert result.items[0].exception_type == "PaymentDeclinedError"
    assert [item.trace_id for item in result.items[0].sample_traces] == [summary.trace_id for summary in summaries[:5]]


def test_issue_span_details_use_bounded_victoria_structure_and_attribute_queries():
    now = timezone.now()
    summaries = tuple(
        _error_span(now - timedelta(seconds=index), trace_id=f"{index:032x}", span_id=f"{index:016x}")
        for index in range(50)
    )
    structure_rows = "\n".join(json.dumps(_vt_span_row(item.trace_id, item.span_id, item.started_at)) for item in summaries)
    attr_rows = "\n".join(
        json.dumps(
            {
                **_vt_span_row(item.trace_id, item.span_id, item.started_at),
                "span_attr:exception.type": "PaymentDeclinedError",
                "span_attr:exception.message": "card 424242 declined",
                "span_attr:exception.stacktrace": "PaymentDeclinedError: declined\n  at charge (payment.py:42)",
                "resource_attr:service.version": "v2",
            }
        )
        for item in summaries
    )
    session = Mock()
    session.get.side_effect = [_vt_response(structure_rows), _vt_response(attr_rows)]
    store = _CountingTraceStore(VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=session))
    query_service = DjangoTelemetryQueryService(trace_store=store)

    result = DjangoTelemetryIssueService(query_service).project(summaries, next_cursor=None)

    assert store.get_trace_calls == 0
    assert store.get_span_details_calls == 1
    queries = [call.kwargs["params"]["query"] for call in session.get.call_args_list]
    structure_queries = [query for query in queries if "| fields " in query]
    attribute_queries = [query for query in queries if "| fields " not in query]
    assert len(structure_queries) <= 2
    assert len(attribute_queries) == 1
    assert "trace_id:in(" in structure_queries[0]
    assert "span_id:in(" in structure_queries[0]
    assert "trace_id:in(" in attribute_queries[0]
    assert "span_id:in(" in attribute_queries[0]
    assert result.items[0].occurrences == 50
    assert result.items[0].exception_type == "PaymentDeclinedError"


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
