import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests
from django.utils import timezone

from apps.apm.adapters import TelemetryStoreUnavailable, VictoriaTracesTraceStore
from apps.apm.services.contracts import TraceSearchQuery

def _response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def _jaeger_trace(now):
    start_us = int(now.timestamp() * 1_000_000)
    return {
        "traceID": "a" * 32,
        "processes": {
            "p1": {
                "serviceName": "checkout",
                "tags": [
                    {"key": "service.namespace", "value": "shop"},
                    {"key": "service.instance.id", "value": "pod-a"},
                    {"key": "deployment.environment", "value": "production"},
                ],
            }
        },
        "spans": [
            {
                "spanID": "1" * 16,
                "operationName": "POST /checkout",
                "processID": "p1",
                "startTime": start_us,
                "duration": 120_000,
                "references": [],
                "tags": [
                    {"key": "span.kind", "value": "server"},
                    {"key": "otel.status_code", "value": "ERROR"},
                    {"key": "Authorization", "value": "Bearer secret"},
                ],
            },
            {
                "spanID": "2" * 16,
                "operationName": "INSERT orders",
                "processID": "p1",
                "startTime": start_us + 10_000,
                "duration": 20_000,
                "references": [{"refType": "CHILD_OF", "spanID": "1" * 16}],
                "tags": [{"key": "span.kind", "value": "client"}],
            },
        ],
    }


def test_search_builds_controlled_resource_filters_and_maps_jaeger_trace():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response({"data": [_jaeger_trace(now)]})
    store = VictoriaTracesTraceStore(endpoint="http://traces.test", session=session)

    page = store.search(
        TraceSearchQuery(
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(minutes=1),
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            instance_id="pod-a",
            limit=20,
        )
    )

    assert len(page.items) == 1
    summary = page.items[0]
    assert summary.trace_id == "a" * 32
    assert summary.root_span_name == "POST /checkout"
    assert summary.status == "error"
    assert summary.span_count == 2
    params = session.get.call_args.kwargs["params"]
    assert params["service"] == "checkout"
    assert params["limit"] == 21
    assert json.loads(params["tags"]) == {
        "resource_attr:deployment.environment": "production",
        "resource_attr:service.namespace": "shop",
        "resource_attr:service.instance.id": "pod-a",
    }


def test_detail_preserves_waterfall_identity_for_server_side_authorization():
    now = timezone.now()
    session = Mock()
    session.get.return_value = _response({"data": [_jaeger_trace(now)]})
    store = VictoriaTracesTraceStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.instance_id == "pod-a"
    assert detail.spans[1].parent_span_id == "1" * 16
    assert detail.spans[0].kind == "server"
    assert detail.spans[0].attributes["Authorization"] == "Bearer secret"


def test_detail_maps_victoriatraces_string_error_tag_to_error_status():
    now = timezone.now()
    raw_trace = _jaeger_trace(now)
    raw_trace["spans"][0]["tags"] = [
        {"key": "span.kind", "value": "server"},
        {"key": "error", "type": "string", "value": "true"},
    ]
    session = Mock()
    session.get.return_value = _response({"data": [raw_trace]})
    store = VictoriaTracesTraceStore(endpoint="http://traces.test", session=session)

    detail = store.get_trace("a" * 32)

    assert detail is not None
    assert detail.spans[0].status == "error"


def test_transport_failures_are_mapped_to_trace_store_degradation():
    session = Mock()
    session.get.side_effect = requests.Timeout("down")
    store = VictoriaTracesTraceStore(endpoint="http://traces.test", session=session)

    with pytest.raises(TelemetryStoreUnavailable, match="查询不可用"):
        store.get_trace("a" * 32)
