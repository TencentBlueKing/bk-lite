from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.services import DjangoTelemetryCatalogService, DjangoTelemetryQueryService
from apps.apm.services.contracts import CatalogDiscovery, SpanDetail, TraceDetail, TracePage, TraceSummary
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _discover(*, organization_ids, instance_id, application_id):
    application = create_application(application_id, tuple(organization_ids))
    result = DjangoTelemetryCatalogService().discover(CatalogDiscovery(application_id, "checkout", instance_id, "production"))
    return application, result.instance


def _summary(trace_id, application_id, instance_id, now):
    return TraceSummary(
        trace_id=trace_id,
        started_at=now,
        duration_ms=25,
        service_namespace=application_id,
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        status="ok",
    )


def _span(span_id, application_id, instance_id, now, *, parent_span_id=None, name="POST /checkout", attributes=None):
    return SpanDetail(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        started_at=now,
        duration_ms=25,
        status="ok",
        attributes=attributes or {},
        service_namespace=application_id,
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        kind="server",
    )


def _detail(trace_id, application_id, instance_id, now, attributes=None, spans=None):
    items = spans or (_span("1" * 16, application_id, instance_id, now, attributes=attributes),)
    root = next((item for item in items if item.parent_span_id is None), items[0])
    return TraceDetail(
        trace_id,
        items,
        root.service_namespace,
        root.service_name,
        root.environment,
        root.instance_id,
    )


def test_search_filters_by_instance_org_and_uses_service_org_when_identity_is_missing(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="pod-allowed", application_id="shop")
    _discover(organization_ids=[20], instance_id="pod-denied", application_id="billing")
    page = TracePage(
        items=(
            _summary("a" * 32, "shop", "pod-allowed", now),
            _summary("b" * 32, "billing", "pod-denied", now),
            _summary("c" * 32, "shop", None, now),
            _summary("d" * 32, "billing", None, now),
        ),
        next_cursor="next",
    )

    def search_traces(query):
        if query.cursor:
            return TracePage((), None)
        return page

    mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces", side_effect=search_traces)

    response = apm_api_client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "service_namespace": "shop", "environment": "production"},
    )

    assert response.status_code == 200
    assert [item["trace_id"] for item in response.data["items"]] == ["a" * 32, "c" * 32]
    assert response.data["next_cursor"] is None


def test_direct_trace_access_is_non_enumerable_and_sensitive_attributes_never_return(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="pod-allowed", application_id="shop")
    _discover(organization_ids=[20], instance_id="pod-denied", application_id="billing")
    allowed = _detail(
        "a" * 32,
        "shop",
        "pod-allowed",
        now,
        {"http.route": "/checkout", "Authorization": "Bearer secret"},
    )
    denied = _detail("b" * 32, "billing", "pod-denied", now)
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[allowed, denied]))
    mocker.patch("apps.apm.views.traces.ApmTraceViewSet._query_service", return_value=service)

    visible = apm_api_client.get(f"/api/v1/apm/traces/{'a' * 32}/")
    forbidden = apm_api_client.get(f"/api/v1/apm/traces/{'b' * 32}/")
    missing = apm_api_client.get(f"/api/v1/apm/traces/{'c' * 32}/")

    assert visible.status_code == 200
    assert visible.data["spans"][0]["attributes"] == {"http.route": "/checkout"}
    assert forbidden.status_code == missing.status_code == 404


def test_mixed_org_trace_detail_returns_only_current_org_spans(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="pod-allowed", application_id="shop")
    _discover(organization_ids=[20], instance_id="pod-denied", application_id="billing")
    hidden_root = _span(
        "2" * 16,
        "billing",
        "pod-denied",
        now,
        name="POST /billing",
        attributes={"Authorization": "Bearer other-org"},
    )
    visible_child = _span(
        "3" * 16,
        "shop",
        "pod-allowed",
        now,
        parent_span_id=hidden_root.span_id,
        attributes={"http.route": "/checkout", "Authorization": "Bearer secret"},
    )
    mixed = _detail("e" * 32, "billing", "pod-denied", now, spans=(hidden_root, visible_child))
    hidden_only = _detail("f" * 32, "billing", "pod-denied", now, spans=(hidden_root,))
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[mixed, hidden_only]))
    mocker.patch("apps.apm.views.traces.ApmTraceViewSet._query_service", return_value=service)

    response = apm_api_client.get(f"/api/v1/apm/traces/{'e' * 32}/")
    forbidden = apm_api_client.get(f"/api/v1/apm/traces/{'f' * 32}/")

    assert response.status_code == 200
    assert [span["span_id"] for span in response.data["spans"]] == [visible_child.span_id]
    assert response.data["spans"][0]["parent_span_id"] == hidden_root.span_id
    assert response.data["spans"][0]["service_namespace"] == "shop"
    assert response.data["spans"][0]["instance_id"] == "pod-allowed"
    assert response.data["spans"][0]["attributes"] == {"http.route": "/checkout"}
    assert response.data["truncated"] is True
    assert response.data["service_namespace"] == "shop"
    assert response.data["service_name"] == "checkout"
    assert response.data["instance_id"] == "pod-allowed"
    assert forbidden.status_code == 404


def test_missing_instance_detail_falls_back_to_service_organization(apm_api_client, mocker):
    now = timezone.now()
    _discover(organization_ids=[10], instance_id="catalog-pod", application_id="shop")
    detail = _detail("d" * 32, "shop", None, now)
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[detail]))
    mocker.patch("apps.apm.views.traces.ApmTraceViewSet._query_service", return_value=service)

    response = apm_api_client.get(f"/api/v1/apm/traces/{'d' * 32}/")

    assert response.status_code == 200


def test_trace_query_limits_and_store_degradation_are_distinct(apm_api_client, mocker):
    now = timezone.now()
    too_wide = apm_api_client.get(
        "/api/v1/apm/traces/",
        {
            "service_name": "checkout",
            "environment": "production",
            "started_at": (now - timedelta(days=8)).isoformat(),
            "ended_at": now.isoformat(),
        },
    )
    query = mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces")
    query.side_effect = TelemetryStoreUnavailable("VictoriaTraces 查询不可用")
    degraded = apm_api_client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "environment": "production"},
    )

    assert too_wide.status_code == 400
    assert too_wide.data["code"] == "invalid_query"
    assert degraded.status_code == 503
    assert degraded.data["code"] == "telemetry_unavailable"


def test_trace_query_capacity_rejection_uses_query_too_large_code(apm_api_client, mocker):
    query = mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces")
    query.side_effect = TelemetryQueryTooLarge("VictoriaTraces 响应超过大小上限")
    response = apm_api_client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "environment": "production"},
    )

    assert response.status_code == 503
    assert response.data["code"] == "query_too_large"


def test_trace_permission_is_checked_before_querying_storage(apm_user_without_permissions, mocker):
    from rest_framework.test import APIClient

    query = mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces")
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "environment": "production"},
    )

    assert response.status_code == 403
    query.assert_not_called()


def test_arbitrary_traceql_is_rejected_instead_of_forwarded(apm_api_client, mocker):
    query = mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces")

    response = apm_api_client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "environment": "production", "q": "{ true }"},
    )

    assert response.status_code == 400
    assert response.data["code"] == "invalid_query"
    query.assert_not_called()
