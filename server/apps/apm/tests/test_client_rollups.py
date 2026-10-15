from datetime import UTC, datetime

import pytest

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTelemetryStore
from apps.apm.adapters.span_aliases import classify_client_db_rollup, classify_client_http_rollup, client_db_statement
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application


def _service(organization=10, namespace="shop", name="checkout"):
    create_application(namespace, (organization,))
    return DjangoTelemetryCatalogService().discover(CatalogDiscovery(namespace, name, "pod-a", "production")).service


def test_classify_client_db_rollup_splits_cache_and_drops_http():
    assert classify_client_db_rollup({"db.system.name": "Redis", "db.system": "other"}) == ("outbound", "Redis")
    assert classify_client_db_rollup({"span_attr:db.system": "postgresql"}) == ("database", "postgresql")
    assert classify_client_db_rollup({"http.method": "GET", "peer.service": "catalog"}) is None
    assert client_db_statement({"span_attr:db.statement": "SELECT sku FROM stock WHERE sku = %s"}, "SELECT") == (
        "SELECT sku FROM stock WHERE sku = %s"
    )
    assert client_db_statement({"name": "SELECT"}, "SELECT") == "SELECT"


def test_classify_client_http_rollup_prefers_method_and_route():
    assert classify_client_http_rollup({"http.method": "POST", "http.route": "/orders"}, "POST") == (
        "http",
        "http",
        "POST /orders",
    )
    assert classify_client_http_rollup(
        {"span_attr:http.request.method": "GET", "span_attr:peer.service": "risk-api"},
        "GET",
    ) == ("http", "risk-api", "GET")
    assert classify_client_http_rollup({"db.system": "postgresql", "http.method": "POST"}) is None


def test_client_db_rollups_query_only_db_client_spans(mocker):
    store = VictoriaTracesTelemetryStore(endpoint="http://traces.test", session=mocker.Mock())
    query_rows = mocker.patch.object(
        store,
        "_query_rows",
        return_value=[
            {
                "name": "SELECT",
                "span_attr:db.system": "postgresql",
                "span_attr:db.statement": "SELECT sku, qty FROM (VALUES (%s, %s::int)) AS stock(sku, qty)",
                "duration_ns": 20_500_000_000,
                "calls": 893,
                "errors": 0,
            },
            {
                "name": "GET",
                "span_attr:db.system.name": "redis",
                "span_attr:db.statement": "GET ?",
                "duration_ns": 11_600_000_000,
                "calls": 63,
                "errors": 1,
            },
            {
                "name": "POST",
                "span_attr:http.method": "POST",
                "span_attr:http.route": "/orders",
                "duration_ns": 4_000_000_000,
                "calls": 12,
                "errors": 0,
            },
            {"name": "GET /stock", "calls": 4, "duration_ns": 1000},
        ],
    )
    started = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    ended = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)

    rows = store.client_db_rollups("shop", "checkout", "production", started, ended)

    query = query_rows.call_args.args[0]
    assert 'kind:="3"' in query
    assert "`span_attr:db.system`:*" in query
    assert "`span_attr:db.system.name`:*" in query
    assert "`span_attr:db.statement`" in query
    assert "`span_attr:db.query.text`" in query
    assert "`span_attr:http.method`" in query
    assert "`span_attr:http.route`" in query
    assert "limit 40" in query
    assert rows == [
        {
            "channel": "database",
            "system": "postgresql",
            "statement": "SELECT sku, qty FROM (VALUES (%s, %s::int)) AS stock(sku, qty)",
            "duration_ms": 20500.0,
            "call_count": 893,
            "error_count": 0,
            "inferred": True,
        },
        {
            "channel": "outbound",
            "system": "redis",
            "statement": "GET ?",
            "duration_ms": 11600.0,
            "call_count": 63,
            "error_count": 1,
            "inferred": True,
        },
        {
            "channel": "http",
            "system": "http",
            "statement": "POST /orders",
            "duration_ms": 4000.0,
            "call_count": 12,
            "error_count": 0,
            "inferred": False,
        },
    ]


@pytest.mark.django_db
def test_client_rollups_endpoint_returns_rows(apm_api_client, mocker):
    service = _service()
    store = mocker.Mock()
    store.client_db_rollups.return_value = [
        {
            "channel": "database",
            "system": "postgresql",
            "statement": "SELECT",
            "duration_ms": 20.0,
            "call_count": 2,
            "error_count": 0,
            "inferred": True,
        }
    ]
    mocker.patch("apps.apm.views.control_plane.VictoriaTracesTelemetryStore", return_value=store)

    missing = apm_api_client.get(f"/api/v1/apm/services/{service.id}/client-rollups/")
    response = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/client-rollups/",
        {"environment": "production"},
    )

    assert missing.status_code == 400
    assert missing.data["code"] == "invalid_query"
    assert response.status_code == 200
    assert response.data["rows"][0]["statement"] == "SELECT"
    assert response.data["rows"][0]["channel"] == "database"
    assert store.client_db_rollups.call_args.args[:3] == ("shop", "checkout", "production")


@pytest.mark.django_db
def test_client_rollups_rejects_unknown_parameters_and_maps_store_failure(apm_api_client, mocker):
    service = _service()
    store = mocker.Mock()
    mocker.patch("apps.apm.views.control_plane.VictoriaTracesTelemetryStore", return_value=store)

    unknown = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/client-rollups/",
        {"environment": "production", "query": "up"},
    )

    assert unknown.status_code == 400
    assert unknown.data["code"] == "invalid_query"
    store.client_db_rollups.assert_not_called()

    store.client_db_rollups.side_effect = TelemetryStoreUnavailable("VictoriaTraces 查询不可用")
    degraded = apm_api_client.get(
        f"/api/v1/apm/services/{service.id}/client-rollups/",
        {"environment": "production"},
    )

    assert degraded.status_code == 503
    assert degraded.data["code"] == "telemetry_unavailable"


@pytest.mark.django_db
def test_client_rollups_hides_services_outside_current_organization(apm_api_client, mocker):
    hidden = _service(20, "hidden", "billing")
    store = mocker.Mock()
    mocker.patch("apps.apm.views.control_plane.VictoriaTracesTelemetryStore", return_value=store)

    response = apm_api_client.get(
        f"/api/v1/apm/services/{hidden.id}/client-rollups/",
        {"environment": "production"},
    )

    assert response.status_code == 404
    store.client_db_rollups.assert_not_called()
