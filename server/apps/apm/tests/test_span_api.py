from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, TelemetryStoreUnavailable
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery, SpanPage, SpanSummary
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _discover(*, organization_ids, instance_id, application_id):
    create_application(application_id, tuple(organization_ids))
    return DjangoTelemetryCatalogService().discover(CatalogDiscovery(application_id, "checkout", instance_id, "production"))


def _span(trace_id, span_id, application_id, instance_id, now, *, status="ok", name="POST /checkout"):
    return SpanSummary(
        trace_id=trace_id,
        span_id=span_id,
        started_at=now,
        duration_ms=12,
        service_namespace=application_id,
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        status=status,
        name=name,
        kind="server",
        http_method="POST",
        http_status_code="200",
    )


def test_span_search_filters_by_instance_org(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="pod-allowed", application_id="shop")
    _discover(organization_ids=[20], instance_id="pod-denied", application_id="billing")
    page = SpanPage(
        items=(
            _span("a" * 32, "1" * 16, "shop", "pod-allowed", now),
            _span("b" * 32, "2" * 16, "billing", "pod-denied", now),
            _span("c" * 32, "3" * 16, "shop", None, now),
        ),
        next_cursor="next",
    )

    def search_spans(query):
        if query.cursor:
            return SpanPage((), None)
        return page

    mocker.patch("apps.apm.views.spans.DjangoTelemetryQueryService.search_spans", side_effect=search_spans)

    response = apm_api_client.get(
        "/api/v1/apm/spans/",
        {"service_name": "checkout", "service_namespace": "shop", "environment": "production"},
    )

    assert response.status_code == 200
    assert [item["span_id"] for item in response.data["items"]] == ["1" * 16, "3" * 16]
    assert response.data["items"][0]["http_method"] == "POST"
    assert response.data["next_cursor"] is None


def test_span_query_rejects_unknown_params_and_maps_degradation(apm_api_client, mocker):
    now = timezone.now()
    unknown = apm_api_client.get(
        "/api/v1/apm/spans/",
        {"service_name": "checkout", "environment": "production", "raw_logsql": "*"},
    )
    too_wide = apm_api_client.get(
        "/api/v1/apm/spans/",
        {
            "service_name": "checkout",
            "environment": "production",
            "started_at": (now - timedelta(days=8)).isoformat(),
            "ended_at": now.isoformat(),
        },
    )
    query = mocker.patch("apps.apm.views.spans.DjangoTelemetryQueryService.search_spans")
    query.side_effect = TelemetryStoreUnavailable("VictoriaTraces 查询不可用")
    degraded = apm_api_client.get(
        "/api/v1/apm/spans/",
        {"service_name": "checkout", "environment": "production"},
    )

    assert unknown.status_code == 400
    assert too_wide.status_code == 400
    assert degraded.status_code == 503
    assert degraded.data["code"] == "telemetry_unavailable"


def test_empty_span_query_searches_current_time_window_without_service_or_environment(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="pod-allowed", application_id="shop")
    allowed = _span("a" * 32, "1" * 16, "shop", "pod-allowed", now)
    search = mocker.patch(
        "apps.apm.views.spans.DjangoTelemetryQueryService.search_spans",
        return_value=SpanPage((allowed,), None),
    )

    response = apm_api_client.get("/api/v1/apm/spans/")

    assert response.status_code == 200
    query = search.call_args.args[0]
    assert query.service_name is None
    assert query.environment is None
    assert query.limit == 20
    assert query.ended_at - query.started_at == timedelta(hours=1)


def test_memory_span_store_filters_controlled_fields():
    now = timezone.now()
    store = InMemoryTraceStore(
        spans=[
            _span("a" * 32, "1" * 16, "shop", "pod-a", now, name="GET /ok"),
            _span("b" * 32, "2" * 16, "shop", "pod-a", now, status="error", name="GET /fail"),
            _span("c" * 32, "3" * 16, "shop", "pod-b", now, name="GET /ok"),
        ]
    )
    from apps.apm.services.contracts import SpanSearchQuery

    page = store.search_spans(
        SpanSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(minutes=1),
            service_name="checkout",
            environment="production",
            service_namespace="shop",
            instance_id="pod-a",
            status="ok",
            span_name="GET /ok",
            kind="server",
            limit=10,
        )
    )
    assert [item.span_id for item in page.items] == ["1" * 16]
