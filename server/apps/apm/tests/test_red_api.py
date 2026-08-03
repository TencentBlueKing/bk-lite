from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable
from apps.apm.services import DjangoIngestSourceService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import (
    CatalogDiscovery,
    ServiceEndpointRed,
    ServiceRed,
    ServiceRedPoint,
)


pytestmark = pytest.mark.django_db


def _service():
    source = DjangoIngestSourceService().create(
        name="source",
        ingest_type="otlp_http",
        organization_ids=[10],
        actor="tester",
    ).source
    return DjangoTelemetryCatalogService().discover(
        CatalogDiscovery(source.id, "shop", "checkout", "pod-a", "production")
    ).service


def test_red_endpoint_requires_one_environment_and_does_not_mix_views(apm_api_client, mocker):
    service = _service()
    metric_query = mocker.patch(
        "apps.apm.views.control_plane.DjangoTelemetryQueryService.service_red",
        return_value=ServiceRed(
            request_rate=12.5,
            error_rate=0.04,
            p95_ms=80,
            p99_ms=140,
            timeseries=(
                ServiceRedPoint(
                    timestamp=timezone.now(),
                    request_rate=10,
                    error_rate=0.1,
                    p95_ms=75,
                    p99_ms=120,
                ),
            ),
            top_endpoints=(
                ServiceEndpointRed(
                    endpoint="GET /checkout",
                    request_rate=8,
                    error_rate=0.05,
                    p95_ms=70,
                    p99_ms=110,
                ),
            ),
        ),
    )

    missing = apm_api_client.get(f"/api/v1/apm/services/{service.id}/metrics/")
    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/?environment=production"
    )

    assert missing.status_code == 400
    assert missing.data["code"] == "invalid_query"
    assert response.status_code == 200
    assert response.data["data_state"] == "available"
    assert response.data["environment"] == "production"
    assert response.data["error_rate"] == 0.04
    assert response.data["timeseries"][0]["request_rate"] == 10
    assert response.data["top_endpoints"][0] == {
        "endpoint": "GET /checkout",
        "request_rate": 8,
        "error_rate": 0.05,
        "p95_ms": 70,
        "p99_ms": 110,
    }
    assert metric_query.call_args.args[0].environment == "production"
    assert metric_query.call_args.args[0].include_breakdown is True


def test_red_endpoint_treats_explicit_empty_environment_as_its_own_view(apm_api_client, mocker):
    service = _service()
    metric_query = mocker.patch(
        "apps.apm.views.control_plane.DjangoTelemetryQueryService.service_red",
        return_value=ServiceRed(request_rate=1, error_rate=0, p95_ms=10, p99_ms=20),
    )

    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/",
        {"environment": ""},
    )

    assert response.status_code == 200
    assert response.data["environment"] == ""
    assert metric_query.call_args.args[0].environment == ""


def test_red_endpoint_rejects_unbounded_windows(apm_api_client):
    service = _service()
    ended_at = timezone.now()
    started_at = ended_at - timedelta(days=2)

    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/",
        {"environment": "production", "started_at": started_at.isoformat(), "ended_at": ended_at.isoformat()},
    )

    assert response.status_code == 400
    assert "24" in response.data["detail"]
    assert response.data["code"] == "invalid_query"


def test_red_endpoint_rejects_arbitrary_promql_parameters(apm_api_client, mocker):
    service = _service()
    metric_query = mocker.patch("apps.apm.views.control_plane.DjangoTelemetryQueryService.service_red")

    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/",
        {"environment": "production", "query": "up"},
    )

    assert response.status_code == 400
    assert response.data["code"] == "invalid_query"
    assert response.json()["code"] == "invalid_query"
    assert response.json()["result"] is False
    metric_query.assert_not_called()


def test_storage_failure_is_distinct_from_legal_empty_metrics(apm_api_client, mocker):
    service = _service()
    metric_query = mocker.patch("apps.apm.views.control_plane.DjangoTelemetryQueryService.service_red")
    metric_query.side_effect = TelemetryStoreUnavailable("VictoriaMetrics 查询不可用")

    degraded = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/?environment=production"
    )
    metric_query.side_effect = None
    metric_query.return_value = ServiceRed(request_rate=None, error_rate=None, p95_ms=None, p99_ms=None)
    empty = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/metrics/?environment=production"
    )

    assert degraded.status_code == 503
    assert degraded.data["code"] == "telemetry_unavailable"
    assert degraded.json()["code"] == "telemetry_unavailable"
    assert empty.status_code == 200
    assert empty.data["data_state"] == "no_data"
    assert empty.data["request_rate"] is None
    assert empty.data["error_rate"] is None
