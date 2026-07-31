from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryTraceStore, TelemetryStoreUnavailable
from apps.apm.services import DjangoIngestSourceService, DjangoTelemetryCatalogService, DjangoTelemetryQueryService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    SpanDetail,
    TraceDetail,
    TracePage,
    TraceSummary,
)


pytestmark = pytest.mark.django_db


def _discover(*, organization_ids, instance_id, source_name):
    source = DjangoIngestSourceService().create(
        name=source_name,
        ingest_type="otlp_http",
        organization_ids=organization_ids,
        actor="tester",
    ).source
    result = DjangoTelemetryCatalogService().discover(
        CatalogDiscovery(source.id, "shop", "checkout", instance_id, "production")
    )
    return source, result.instance


def _summary(trace_id, instance_id, source_id, now):
    return TraceSummary(
        trace_id=trace_id,
        started_at=now,
        duration_ms=25,
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        status="ok",
        ingest_source_id=source_id,
    )


def _detail(trace_id, instance_id, source_id, now, attributes=None):
    span = SpanDetail(
        span_id="1" * 16,
        parent_span_id=None,
        name="POST /checkout",
        started_at=now,
        duration_ms=25,
        status="ok",
        attributes=attributes or {},
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        instance_id=instance_id,
        kind="server",
        ingest_source_id=source_id,
    )
    return TraceDetail(
        trace_id,
        (span,),
        "shop",
        "checkout",
        "production",
        instance_id,
        source_id,
    )


def test_search_filters_by_instance_org_and_uses_source_org_only_when_identity_is_missing(
    apm_api_client, mocker
):
    now = timezone.now()
    allowed_source, _ = _discover(organization_ids=[10], instance_id="pod-allowed", source_name="allowed")
    denied_source, _ = _discover(organization_ids=[20], instance_id="pod-denied", source_name="denied")
    page = TracePage(
        items=(
            _summary("a" * 32, "pod-allowed", allowed_source.id, now),
            _summary("b" * 32, "pod-denied", denied_source.id, now),
            _summary("c" * 32, None, allowed_source.id, now),
            _summary("d" * 32, None, denied_source.id, now),
        ),
        next_cursor="next",
    )
    mocker.patch("apps.apm.views.traces.DjangoTelemetryQueryService.search_traces", return_value=page)

    response = apm_api_client.get(
        "/api/v1/apm/traces/",
        {"service_name": "checkout", "service_namespace": "shop", "environment": "production"},
    )

    assert response.status_code == 200
    assert [item["trace_id"] for item in response.data["items"]] == ["a" * 32, "c" * 32]
    assert response.data["next_cursor"] == "next"


def test_direct_trace_access_is_non_enumerable_and_sensitive_attributes_never_return(
    apm_api_client, mocker
):
    now = timezone.now()
    allowed_source, _ = _discover(organization_ids=[10], instance_id="pod-allowed", source_name="allowed")
    denied_source, _ = _discover(organization_ids=[20], instance_id="pod-denied", source_name="denied")
    allowed = _detail(
        "a" * 32,
        "pod-allowed",
        allowed_source.id,
        now,
        {"http.route": "/checkout", "Authorization": "Bearer secret"},
    )
    denied = _detail("b" * 32, "pod-denied", denied_source.id, now)
    service = DjangoTelemetryQueryService(trace_store=InMemoryTraceStore(details=[allowed, denied]))
    mocker.patch("apps.apm.views.traces.ApmTraceViewSet._query_service", return_value=service)

    visible = apm_api_client.get(f"/api/v1/apm/traces/{'a' * 32}/")
    forbidden = apm_api_client.get(f"/api/v1/apm/traces/{'b' * 32}/")
    missing = apm_api_client.get(f"/api/v1/apm/traces/{'c' * 32}/")

    assert visible.status_code == 200
    assert visible.data["spans"][0]["attributes"] == {"http.route": "/checkout"}
    assert forbidden.status_code == missing.status_code == 404


def test_missing_instance_detail_falls_back_to_trusted_source_organization(apm_api_client, mocker):
    now = timezone.now()
    source, _ = _discover(organization_ids=[10], instance_id="catalog-pod", source_name="allowed")
    detail = _detail("d" * 32, None, source.id, now)
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
