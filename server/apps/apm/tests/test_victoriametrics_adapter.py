from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaMetricsMetricStore
from apps.apm.services.contracts import InstanceActivityQuery, ServiceMetricQuery


def _response(result):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"status": "success", "data": {"result": result}}
    return response


def test_service_red_uses_environment_scoped_entry_spans_and_histogram_quantiles():
    now = timezone.now()
    session = Mock()
    session.get.side_effect = [
        _response([{"value": [0, "20"]}]),
        _response([{"value": [0, "2"]}]),
        _response([{"value": [0, "125"]}]),
        _response([{"value": [0, "250"]}]),
    ]
    store = VictoriaMetricsMetricStore(endpoint="http://metrics.test", session=session)

    red = store.service_red(
        ServiceMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=now - timedelta(minutes=5),
            ended_at=now,
        )
    )

    assert red.request_rate == 20
    assert red.error_rate == 0.1
    assert red.p95_ms == 125
    assert red.p99_ms == 250
    queries = [call.kwargs["params"]["query"] for call in session.get.call_args_list]
    assert all('deployment_environment="production"' in query for query in queries)
    assert all('span_kind=~"SPAN_KIND_SERVER|SPAN_KIND_CONSUMER"' in query for query in queries)
    assert "histogram_quantile(0.95" in queries[2]
    assert "histogram_quantile(0.99" in queries[3]


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
