import pytest
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    MetricDataState,
    ServiceErrorBreakdown,
    ServiceErrorSampleTrace,
    ServiceErrorType,
    ServiceFailedEndpoint,
    SpanSummary,
)
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _service(organization=10, namespace="shop", name="checkout"):
    create_application(namespace, (organization,))
    return DjangoTelemetryCatalogService().discover(
        CatalogDiscovery(namespace, name, "pod-a", "production")
    ).service


def _breakdown(**overrides):
    now = timezone.now()
    payload = dict(
        request_count=10,
        error_count=4,
        error_rate=0.4,
        data_state=MetricDataState.AVAILABLE,
        failed_endpoints=(
            ServiceFailedEndpoint("POST /checkout", 3, 8, 0.375),
            ServiceFailedEndpoint("GET /products", 1, 2, 0.5),
        ),
        other_error_count=0,
        error_types=(
            ServiceErrorType(
                error_type="payment_declined",
                message="",
                count=2,
                location="downstream",
                last_seen_at=now,
                sample_traces=(
                    ServiceErrorSampleTrace("a" * 32, "1" * 16, "POST /orders", now),
                ),
            ),
        ),
        recent_failures=(
            SpanSummary(
                trace_id="b" * 32,
                span_id="2" * 16,
                started_at=now,
                duration_ms=80,
                service_namespace="shop",
                service_name="checkout",
                environment="production",
                instance_id="pod-a",
                status="error",
                name="POST /checkout",
                kind="server",
                http_method="POST",
                http_status_code="502",
            ),
        ),
    )
    payload.update(overrides)
    return ServiceErrorBreakdown(**payload)


def test_error_breakdown_endpoint_returns_entry_counts_and_error_types(apm_api_client, mocker):
    service = _service()
    query = mocker.patch(
        "apps.apm.views.control_plane.DjangoTelemetryQueryService.service_error_breakdown",
        return_value=_breakdown(),
    )

    missing = apm_api_client.get(f"/api/v1/apm/services/{service.id}/error-breakdown/")
    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/error-breakdown/",
        {"environment": "production", "sample_limit": 20},
    )

    assert missing.status_code == 400
    assert missing.data["code"] == "invalid_query"
    assert response.status_code == 200
    assert response.data["data_state"] == "available"
    assert response.data["request_count"] == 10
    assert response.data["error_count"] == 4
    assert response.data["failed_endpoints"][0]["endpoint"] == "POST /checkout"
    assert response.data["error_types"][0]["error_type"] == "payment_declined"
    assert response.data["error_types"][0]["location"] == "downstream"
    assert response.data["recent_failures"][0]["trace_id"] == "b" * 32
    assert "exception_type" not in response.data["recent_failures"][0]
    assert query.call_args.args[0].environment == "production"
    assert query.call_args.args[0].sample_limit == 20
    assert query.call_args.args[0].service_name == "checkout"


def test_error_breakdown_rejects_unknown_parameters_and_maps_store_failure(apm_api_client, mocker):
    service = _service()
    query = mocker.patch("apps.apm.views.control_plane.DjangoTelemetryQueryService.service_error_breakdown")

    unknown = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/error-breakdown/",
        {"environment": "production", "query": "up"},
    )

    assert unknown.status_code == 400
    assert unknown.data["code"] == "invalid_query"
    query.assert_not_called()

    query.side_effect = TelemetryStoreUnavailable("VictoriaTraces 查询不可用")
    degraded = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/error-breakdown/",
        {"environment": "production"},
    )

    assert degraded.status_code == 503
    assert degraded.data["code"] == "telemetry_unavailable"


def test_error_breakdown_hides_services_outside_current_organization(apm_api_client, mocker):
    hidden = _service(20, "hidden", "billing")
    query = mocker.patch("apps.apm.views.control_plane.DjangoTelemetryQueryService.service_error_breakdown")

    response = apm_api_client.get(
        f"/api/v1/apm/services/{hidden.id}/error-breakdown/",
        {"environment": "production"},
    )

    assert response.status_code == 404
    query.assert_not_called()
