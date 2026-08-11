import base64

import pytest
import requests

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.datasource_preview.base import ConnectorError, PreviewResult
from apps.operation_analysis.services.datasource_preview.prometheus_client import (
    PrometheusHttpClient,
    build_auth_headers,
    normalize_prometheus_origin,
)
from apps.operation_analysis.services.datasource_preview.prometheus import PrometheusConnectorExecutor
from apps.operation_analysis.services.datasource_preview.prometheus_transform import (
    clamp_max_series,
    format_series_legend,
    transform_instant_result,
    transform_range_result,
)
from apps.operation_analysis.services.datasource_preview.registry import get_preview_executor


def test_prometheus_source_type_constant():
    assert DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS == "prometheus"
    assert ("prometheus", "Prometheus") in DataSourceAPIModel.SOURCE_TYPE_CHOICES


def test_preview_result_includes_optional_warnings():
    result = PreviewResult(items=[{"a": 1}], count=1, fields=[], warnings=["truncated"])
    assert result.as_dict()["warnings"] == ["truncated"]


@pytest.mark.parametrize(
    "raw",
    [
        "https://prom.example.com",
        "https://prom.example.com/",
        "http://10.0.0.1:9090",
    ],
)
def test_normalize_prometheus_origin_accepts_origin(raw):
    origin = normalize_prometheus_origin(raw)
    assert origin.startswith("http")
    assert "/api/v1" not in origin


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ftp://x",
        "https://user:pass@host",
        "https://prom.example.com/api/v1/query",
        "not-a-url",
    ],
)
def test_normalize_prometheus_origin_rejects_invalid(raw):
    with pytest.raises(ConnectorError):
        normalize_prometheus_origin(raw)


def test_build_auth_headers_basic_and_bearer():
    assert build_auth_headers({}) == {}
    assert build_auth_headers({"auth_type": "none"}) == {}
    basic = build_auth_headers({"auth_type": "basic", "username": "u", "password": "p"})
    assert basic["Authorization"].startswith("Basic ")
    expected = base64.b64encode(b"u:p").decode("ascii")
    assert basic["Authorization"] == f"Basic {expected}"
    bearer = build_auth_headers({"auth_type": "bearer", "token": "tok"})
    assert bearer == {"Authorization": "Bearer tok"}


@pytest.mark.parametrize(
    "config",
    [
        {"auth_type": "basic", "username": "u"},
        {"auth_type": "basic", "password": "p"},
        {"auth_type": "bearer"},
    ],
)
def test_build_auth_headers_missing_credentials_raises(config):
    with pytest.raises(ConnectorError):
        build_auth_headers(config)


def test_query_range_sends_expected_request():
    calls = []

    class FakeResponse:
        status_code = 200
        headers = {"content-length": "32"}

        def iter_content(self, chunk_size):
            yield b'{"status":"success","data":{"resultType":"matrix","result":[]}}'

        def close(self):
            return None

        def json(self):
            return {"status": "success", "data": {"resultType": "matrix", "result": []}}

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    client = PrometheusHttpClient(http_client=FakeClient())
    payload = client.query_range(
        {"url": "https://prom.example.com", "auth_type": "bearer", "token": "t", "timeout_seconds": 15},
        query="up",
        start="1700000000",
        end="1700003600",
        step="1m",
    )
    assert payload["status"] == "success"
    assert calls[0]["url"] == "https://prom.example.com/api/v1/query_range"
    assert calls[0]["params"]["query"] == "up"
    assert calls[0]["headers"]["Authorization"] == "Bearer t"
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["stream"] is True


def _success_json_response(body: bytes | None = None):
    payload = body or b'{"status":"success","data":{"resultType":"vector","result":[]}}'

    class FakeResponse:
        status_code = 200
        headers = {"content-length": str(len(payload))}

        def iter_content(self, chunk_size):
            yield payload

        def close(self):
            return None

    return FakeResponse()


def test_query_sends_expected_request():
    calls = []

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            return _success_json_response()

    client = PrometheusHttpClient(http_client=FakeClient())
    payload = client.query({"url": "https://prom.example.com"}, query="up{job='api'}")
    assert payload["status"] == "success"
    assert calls[0]["url"] == "https://prom.example.com/api/v1/query"
    assert calls[0]["params"] == {"query": "up{job='api'}"}


def test_healthy_succeeds_via_health_endpoint():
    calls = []

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            return _success_json_response(b"OK")

    client = PrometheusHttpClient(http_client=FakeClient())
    client.healthy({"url": "https://prom.example.com"})
    assert len(calls) == 1
    assert calls[0]["url"] == "https://prom.example.com/-/healthy"


def test_healthy_falls_back_to_buildinfo():
    calls = []

    class UnhealthyResponse:
        status_code = 503
        headers = {}

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            calls.append(kwargs)
            if kwargs["url"].endswith("/-/healthy"):
                return UnhealthyResponse()
            return _success_json_response()

    client = PrometheusHttpClient(http_client=FakeClient())
    client.healthy({"url": "https://prom.example.com"})
    assert len(calls) == 2
    assert calls[0]["url"] == "https://prom.example.com/-/healthy"
    assert calls[1]["url"] == "https://prom.example.com/api/v1/status/buildinfo"


def test_request_json_maps_http_401_to_auth_failed():
    class FakeResponse:
        status_code = 401
        headers = {}

        def iter_content(self, chunk_size):
            return iter([])

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            return FakeResponse()

    client = PrometheusHttpClient(http_client=FakeClient())
    with pytest.raises(ConnectorError) as exc_info:
        client.query({"url": "https://prom.example.com"}, query="up")
    assert exc_info.value.code == "prometheus_auth_failed"
    assert exc_info.value.status_code == 400


def test_request_json_maps_prometheus_error_status():
    class FakeResponse:
        status_code = 200
        headers = {"content-length": "52"}

        def iter_content(self, chunk_size):
            yield b'{"status":"error","errorType":"bad_data","error":"parse error at 1:1"}'

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            return FakeResponse()

    client = PrometheusHttpClient(http_client=FakeClient())
    with pytest.raises(ConnectorError) as exc_info:
        client.query({"url": "https://prom.example.com"}, query="bad{")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "prometheus_query_error"
    assert "parse error at 1:1" in exc_info.value.message


def test_request_json_maps_timeout_to_502():
    class FakeClient:
        def request(self, **kwargs):
            raise requests.Timeout("read timed out")

    client = PrometheusHttpClient(http_client=FakeClient())
    with pytest.raises(ConnectorError) as exc_info:
        client.query({"url": "https://prom.example.com"}, query="up")
    assert exc_info.value.code == "prometheus_timeout"
    assert exc_info.value.status_code == 502


@pytest.mark.parametrize("timeout_seconds", ["abc", {}, []])
def test_resolve_timeout_rejects_invalid_values(timeout_seconds):
    client = PrometheusHttpClient()
    with pytest.raises(ConnectorError) as exc_info:
        client._resolve_timeout({"timeout_seconds": timeout_seconds})
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    ("timeout_seconds", "expected_read_timeout"),
    [
        (None, 30),
        (0, 1),
        (-5, 1),
        (15, 15),
        (120, 60),
    ],
)
def test_resolve_timeout_clamps_read_timeout(timeout_seconds, expected_read_timeout):
    client = PrometheusHttpClient()
    config = {} if timeout_seconds is None else {"timeout_seconds": timeout_seconds}
    _, read_timeout = client._resolve_timeout(config)
    assert read_timeout == expected_read_timeout


def test_request_json_maps_invalid_json_to_502():
    class FakeResponse:
        status_code = 200
        headers = {"content-length": "4"}

        def iter_content(self, chunk_size):
            yield b"not-json"

        def close(self):
            return None

    class FakeClient:
        def request(self, **kwargs):
            return FakeResponse()

    client = PrometheusHttpClient(http_client=FakeClient())
    with pytest.raises(ConnectorError) as exc_info:
        client.query({"url": "https://prom.example.com"}, query="up")
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "prometheus_invalid_response"


def test_format_series_legend():
    assert format_series_legend({"__name__": "up", "job": "a", "instance": "1"}) == 'up{instance="1",job="a"}'
    assert format_series_legend({}) == "series"
    assert format_series_legend({"__name__": "up"}) == "up"
    assert format_series_legend({"job": "x"}) == '{job="x"}'


def test_transform_range_empty_result():
    data, warnings = transform_range_result({"result": []})
    assert data == []
    assert warnings is None


def test_transform_instant_empty_result():
    data, warnings = transform_instant_result({"result": []})
    assert data == []
    assert warnings is None


def test_transform_range_single_and_multi():
    matrix = {
        "result": [
            {"metric": {"__name__": "up", "instance": "a"}, "values": [[1700, "1"], [1701, "0"]]},
            {"metric": {"__name__": "up", "instance": "b"}, "values": [[1700, "1"]]},
        ]
    }
    data, warnings = transform_range_result(matrix, max_series=10)
    assert isinstance(data, dict)
    assert 'up{instance="a"}' in data
    assert data['up{instance="a"}'][0] == {"name": 1700, "value": "1"}
    assert warnings is None

    data2, warnings2 = transform_range_result(matrix, max_series=1)
    assert isinstance(data2, list)  # single series after truncate -> LIST not dict
    assert warnings2 and "截断" in warnings2[0]


def test_transform_range_single_series_returns_list():
    matrix = {
        "result": [
            {"metric": {"__name__": "up", "instance": "a"}, "values": [[1700, "1"], [1701, "0"]]},
        ]
    }
    data, warnings = transform_range_result(matrix, max_series=10)
    assert isinstance(data, list)
    assert data == [{"name": 1700, "value": "1"}, {"name": 1701, "value": "0"}]
    assert warnings is None


def test_transform_instant_multi_to_rows():
    vector = {
        "result": [
            {"metric": {"__name__": "up", "instance": "a"}, "value": [1700, "1"]},
            {"metric": {"__name__": "up", "instance": "b"}, "value": [1700, "0"]},
        ]
    }
    data, warnings = transform_instant_result(vector, max_series=10)
    assert data == [
        {"name": 'up{instance="a"}', "value": "1"},
        {"name": 'up{instance="b"}', "value": "0"},
    ]


def test_transform_instant_truncation_warning():
    vector = {
        "result": [
            {"metric": {"__name__": "up", "instance": "a"}, "value": [1700, "1"]},
            {"metric": {"__name__": "up", "instance": "b"}, "value": [1700, "0"]},
        ]
    }
    data, warnings = transform_instant_result(vector, max_series=1)
    assert len(data) == 1
    assert warnings and "截断" in warnings[0]


def test_clamp_max_series():
    assert clamp_max_series(None) == 20
    assert clamp_max_series(100) == 50
    assert clamp_max_series(0) == 1
    assert clamp_max_series("abc") == 20


class FakeClientUnused:
    def query_range(self, *args, **kwargs):
        raise AssertionError("query_range should not be called")

    def query(self, *args, **kwargs):
        raise AssertionError("query should not be called")

    def healthy(self, connection_config):
        raise AssertionError("healthy should not be called")


def test_registry_returns_prometheus_executor():
    assert isinstance(get_preview_executor("prometheus"), PrometheusConnectorExecutor)


def test_executor_execute_instant_uses_time_range_end():
    class FakeClient:
        def query(self, connection_config, query, time=None):
            assert query == "up"
            assert time == "1767229200"
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {"__name__": "up"}, "value": [1700, "1"]}],
                },
            }

        def healthy(self, connection_config):
            return None

    executor = PrometheusConnectorExecutor(client=FakeClient())
    result = executor.execute(
        {"url": "https://prom.example.com", "auth_type": "none"},
        {
            "query": "up",
            "query_type": "instant",
            "time_range": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
        },
    )
    assert result.data == [{"name": "up", "value": "1"}]
    assert result.warnings is None


def test_executor_execute_instant_without_time_range_omits_time():
    class FakeClient:
        def query(self, connection_config, query, time=None):
            assert query == "up"
            assert time is None
            return {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [{"metric": {"__name__": "up"}, "value": [1700, "1"]}],
                },
            }

        def healthy(self, connection_config):
            return None

    executor = PrometheusConnectorExecutor(client=FakeClient())
    result = executor.execute(
        {"url": "https://prom.example.com", "auth_type": "none"},
        {"query": "up", "query_type": "instant"},
    )
    assert result.data == [{"name": "up", "value": "1"}]
    assert result.warnings is None


def test_executor_execute_range_passes_params():
    class FakeClient:
        def query_range(self, connection_config, query, start, end, step):
            assert query == "up"
            assert step == "1m"
            return {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [{"metric": {"__name__": "up"}, "values": [[1700, "1"]]}],
                },
            }

        def healthy(self, connection_config):
            return None

    executor = PrometheusConnectorExecutor(client=FakeClient())
    result = executor.execute(
        {"url": "https://prom.example.com", "auth_type": "none"},
        {
            "query": "up",
            "query_type": "range",
            "time_range": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
            "step": "1m",
            "max_series": 20,
        },
    )
    assert result.data == [{"name": 1700, "value": "1"}]
    assert result.warnings is None


def test_executor_rejects_range_over_31_days():
    executor = PrometheusConnectorExecutor(client=FakeClientUnused())
    with pytest.raises(ConnectorError) as exc:
        executor.execute(
            {"url": "https://prom.example.com", "auth_type": "none"},
            {
                "query": "up",
                "query_type": "range",
                "time_range": ["2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z"],
                "step": "1m",
            },
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "prometheus_range_too_large"


def test_executor_test_connection_calls_healthy():
    calls = []

    class FakeClient:
        def healthy(self, connection_config):
            calls.append(connection_config)

        def query_range(self, *args, **kwargs):
            raise AssertionError("query_range should not be called")

        def query(self, *args, **kwargs):
            raise AssertionError("query should not be called")

    config = {"url": "https://prom.example.com", "auth_type": "none"}
    executor = PrometheusConnectorExecutor(client=FakeClient())
    executor.test_connection(config)
    assert calls == [config]


def test_executor_preview_flattens_multi_series():
    class FakeClient:
        def query_range(self, connection_config, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"__name__": "up", "instance": "a"},
                            "values": [[1700, "1"], [1701, "0"]],
                        },
                        {
                            "metric": {"__name__": "up", "instance": "b"},
                            "values": [[1700, "1"]],
                        },
                    ],
                },
            }

        def healthy(self, connection_config):
            return None

    executor = PrometheusConnectorExecutor(client=FakeClient())
    result = executor.preview(
        {"url": "https://prom.example.com", "auth_type": "none"},
        {
            "query": "up",
            "query_type": "range",
            "time_range": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
            "step": "1m",
        },
    )
    assert result.count == 3
    assert len(result.items) == 3
    assert all({"series", "name", "value"} <= set(item.keys()) for item in result.items)
    assert result.fields
    field_keys = {field["key"] for field in result.fields}
    assert {"series", "name", "value"} <= field_keys
