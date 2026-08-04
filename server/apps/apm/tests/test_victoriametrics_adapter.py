from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaMetricsMetricStore
from apps.apm.services.contracts import InstanceActivityQuery, MetricDataState, ServiceMetricQuery, SloMetricQuery


def _response(result):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "success", "data": {"result": result}}
    return response


def _range_response(result):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "success", "data": {"result": result}}
    return response


def test_service_red_uses_environment_scoped_entry_spans_and_histogram_quantiles():
    now = timezone.now()
    earlier = now - timedelta(minutes=1)
    session = Mock()
    session.get.side_effect = [
        _response([{"value": [0, "20"]}]),
        _response([{"value": [0, "2"]}]),
        _response([{"value": [0, "125"]}]),
        _response([{"value": [0, "250"]}]),
        _range_response([{"values": [[earlier.timestamp(), "10"], [now.timestamp(), "20"]]}]),
        _range_response([{"values": [[earlier.timestamp(), "1"], [now.timestamp(), "2"]]}]),
        _range_response([{"values": [[earlier.timestamp(), "100"], [now.timestamp(), "125"]]}]),
        _range_response([{"values": [[earlier.timestamp(), "180"], [now.timestamp(), "250"]]}]),
        _response([
            {"metric": {"span_name": "GET /checkout"}, "value": [0, "12"]},
            {"metric": {"span_name": "GET /health"}, "value": [0, "8"]},
        ]),
        _response([
            {"metric": {"span_name": "GET /checkout"}, "value": [0, "1.2"]},
        ]),
        _response([
            {"metric": {"span_name": "GET /checkout"}, "value": [0, "110"]},
            {"metric": {"span_name": "GET /health"}, "value": [0, "20"]},
        ]),
        _response([
            {"metric": {"span_name": "GET /checkout"}, "value": [0, "210"]},
            {"metric": {"span_name": "GET /health"}, "value": [0, "30"]},
        ]),
    ]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=now - timedelta(minutes=5),
            ended_at=now,
            include_breakdown=True,
        )
    )

    assert red.request_rate == 20
    assert red.error_rate == 0.1
    assert red.p95_ms == 125
    assert red.p99_ms == 250
    assert [(point.request_rate, point.error_rate) for point in red.timeseries] == [
        (10, 0.1),
        (20, 0.1),
    ]
    assert [(item.endpoint, item.request_rate) for item in red.top_endpoints] == [
        ("GET /checkout", 12),
        ("GET /health", 8),
    ]
    assert red.top_endpoints[0].error_rate == pytest.approx(0.1)
    assert red.top_endpoints[1].error_rate == 0
    queries = [call.kwargs["params"]["query"] for call in session.get.call_args_list]
    assert all('deployment_environment="production"' in query for query in queries)
    assert all('span_kind=~"SPAN_KIND_SERVER|SPAN_KIND_CONSUMER"' in query for query in queries)
    assert "histogram_quantile(0.95" in queries[2]
    assert "histogram_quantile(0.99" in queries[3]
    assert all(call.args[0].endswith("/api/v1/query_range") for call in session.get.call_args_list[4:8])
    assert all(int(call.kwargs["params"]["step"]) >= 15 for call in session.get.call_args_list[4:8])
    assert "by (span_name)" in queries[8]
    assert "by (le,span_name)" in queries[10]


def test_service_red_preserves_no_samples_instead_of_fabricating_zero_metrics():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [_response([]), _response([]), _response([]), _response([])]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=now - timedelta(minutes=1),
            ended_at=now,
        )
    )

    assert red.request_rate is None
    assert red.error_rate is None
    assert red.p95_ms is None
    assert red.p99_ms is None


def test_service_red_treats_missing_error_series_as_zero_when_requests_exist():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response([{"value": [0, "20"]}]),
        _response([]),
        _response([{"value": [0, "125"]}]),
        _response([{"value": [0, "250"]}]),
    ]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=now - timedelta(minutes=1),
            ended_at=now,
        )
    )

    assert red.request_rate == 20
    assert red.error_rate == 0
    assert red.p95_ms == 125
    assert red.p99_ms == 250


def test_slo_measurement_uses_real_event_ratios_and_endpoint_scope():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response([{"value": [0, "100"]}]),
        _response([{"value": [0, "0.5"]}]),
    ]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    measurement = store.slo_measurement(
        SloMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            endpoint="POST /checkout",
            sli_type="availability",
            latency_threshold_ms=None,
            started_at=now - timedelta(days=7),
            ended_at=now,
        )
    )

    assert measurement.compliance_percent == 99.5
    assert measurement.good_rate == 99.5
    assert measurement.data_state == MetricDataState.AVAILABLE
    queries = [call.kwargs["params"]["query"] for call in session.get.call_args_list]
    assert all('span_name="POST /checkout"' in query for query in queries)
    assert 'status_code="STATUS_CODE_ERROR"' in queries[1]


def test_latency_slo_uses_histogram_bucket_and_preserves_no_samples():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response([{"value": [0, "20"]}]),
        _response([{"value": [0, "19"]}]),
        _response([]),
    ]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)
    query = SloMetricQuery(
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        sli_type="latency_p95",
        latency_threshold_ms=250,
        started_at=now - timedelta(days=30),
        ended_at=now,
    )

    measurement = store.slo_measurement(query)
    no_data = store.slo_measurement(query)

    assert measurement.compliance_percent == 95
    assert 'le="250"' in session.get.call_args_list[1].kwargs["params"]["query"]
    assert no_data.data_state == MetricDataState.NO_DATA
    assert no_data.compliance_percent is None


def test_instance_activity_only_accepts_complete_trusted_catalog_dimensions():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response(
        [
            {
                "metric": {
                    "service_namespace": "shop",
                    "service_name": "checkout",
                    "service_instance_id": "pod-a",
                    "deployment_environment": "production",
                    "service_version": "1.0",
                    "bk_ingest_source_id": "11111111-2222-4333-8444-555555555555",
                },
                "value": [0, str(now.timestamp())],
            },
            {
                "metric": {
                    "service_name": "ignored-invalid-source",
                    "bk_ingest_source_id": "not-a-uuid",
                },
                "value": [0, str(now.timestamp())],
            },
        ]
    )
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    activities = store.instance_activity(
        InstanceActivityQuery(started_at=now - timedelta(minutes=20), ended_at=now)
    )

    assert len(activities) == 1
    assert activities[0].instance_id == "pod-a"
    assert activities[0].last_seen_at == now
    promql = session.get.call_args.kwargs["params"]["query"]
    assert "tlast_over_time" in promql
    assert "bk_ingest_source_id" in promql


def test_transport_failures_are_mapped_to_degraded_store_error():
    session = Mock()
    session.get.side_effect = requests.Timeout("down")
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)
    now = timezone.now()

    with pytest.raises(TelemetryStoreUnavailable, match="查询不可用"):
        store.instance_activity(InstanceActivityQuery(started_at=now - timedelta(minutes=20), ended_at=now))


def test_non_finite_metric_values_never_escape_the_store_contract():
    assert VictoriaMetricsMetricStore._scalar([{"value": [0, "NaN"]}]) == 0
    assert VictoriaMetricsMetricStore._range_values(
        [{"values": [[1, "NaN"], [2, "Infinity"], [3, "4"]]}]
    ) == {1.0: 0.0, 2.0: 0.0, 3.0: 4.0}
    assert VictoriaMetricsMetricStore._endpoint_values(
        [
            {"metric": {"span_name": "GET /bad"}, "value": [0, "NaN"]},
            {"metric": {"span_name": "GET /ok"}, "value": [0, "2"]},
        ]
    ) == {"GET /ok": 2.0}
