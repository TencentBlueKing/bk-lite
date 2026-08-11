import pytest

from core.collection.contracts import AccessProbeStatus
from plugins.inputs.influxdb.influxdb_info import InfluxdbInfo
from service.collection_service import CollectionService


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


@pytest.mark.asyncio
async def test_probe_validates_http_health_and_operator_token(monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return FakeResponse(body={"status": "pass", "version": "2.7.5"})
        assert kwargs["headers"] == {"Authorization": "Token invalid-token"}
        return FakeResponse(status_code=401)

    monkeypatch.setattr(
        "plugins.inputs.influxdb.influxdb_info.requests.get", fake_get
    )

    result = await InfluxdbInfo(
        {
            "host": "influx.local",
            "token": "invalid-token",
            "timeout": 5,
        }
    ).probe()

    assert result.status == AccessProbeStatus.AUTH_FAILED
    assert result.error_code == "authentication_failed"
    assert "invalid-token" not in result.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_status", "expected_error"),
    [
        (403, AccessProbeStatus.CAPABILITY_DENIED, "capability_denied"),
        (429, AccessProbeStatus.RATE_LIMITED, "rate_limited"),
        (503, AccessProbeStatus.SERVICE_UNAVAILABLE, "service_unavailable"),
    ],
)
async def test_probe_classifies_http_failure_without_retrying_credentials(
    monkeypatch, status_code, expected_status, expected_error
):
    def fake_get(url, **_kwargs):
        if url.endswith("/health"):
            return FakeResponse(body={"status": "pass", "version": "2.7.5"})
        return FakeResponse(status_code=status_code)

    monkeypatch.setattr(
        "plugins.inputs.influxdb.influxdb_info.requests.get", fake_get
    )

    result = await InfluxdbInfo(
        {"host": "influx.local", "token": "must-not-leak", "timeout": 5}
    ).probe()

    assert result.status == expected_status
    assert result.error_code == expected_error
    assert "must-not-leak" not in result.detail


@pytest.mark.asyncio
async def test_probe_keeps_tls_validation_failure_distinct(monkeypatch):
    import requests

    def invalid_certificate(*_args, **_kwargs):
        raise requests.exceptions.SSLError("certificate verify failed")

    monkeypatch.setattr(
        "plugins.inputs.influxdb.influxdb_info.requests.get",
        invalid_certificate,
    )

    result = await InfluxdbInfo(
        {
            "host": "influx.local",
            "ssl": True,
            "verify_tls": True,
            "timeout": 5,
        }
    ).probe()

    assert result.status == AccessProbeStatus.TLS_VALIDATION_FAILED
    assert result.error_code == "tls_validation_failed"


@pytest.mark.asyncio
async def test_v2_without_token_collects_health_only(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(body={"status": "pass", "version": "2.7.5"})

    monkeypatch.setattr("plugins.inputs.influxdb.influxdb_info.requests.get", fake_get)

    result = await InfluxdbInfo(
        {"host": "influx.local", "port": 8086, "ssl": False, "verify_tls": True}
    ).list_all_resources()

    assert result["success"] is True
    assert result["result"]["influxdb"] == [
        {
            "version": "2.7.5",
            "auth_enabled": "true",
            "ip_addr": "influx.local",
            "port": 8086,
            "https_enabled": "false",
        }
    ]
    assert [call[0] for call in calls] == ["http://influx.local:8086/health"]
    assert calls[0][1]["verify"] is True


@pytest.mark.asyncio
async def test_v2_with_operator_token_collects_full_config(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/health"):
            return FakeResponse(body={"status": "pass", "version": "2.7.5"})
        return FakeResponse(
            body={
                "config": {
                    "engine-path": "/var/lib/influxdb2/engine",
                    "bolt-path": "/var/lib/influxdb2/influxd.bolt",
                    "storage-engine": "tsm1",
                    "http-bind-address": ":8086",
                    "query-concurrency": 10,
                }
            }
        )

    monkeypatch.setattr("plugins.inputs.influxdb.influxdb_info.requests.get", fake_get)

    result = await InfluxdbInfo(
        {
            "host": "influx.local",
            "port": 8443,
            "ssl": True,
            "verify_tls": False,
            "token": "operator-secret",
        }
    ).list_all_resources()

    row = result["result"]["influxdb"][0]
    assert row["data_dir"] == "/var/lib/influxdb2/engine"
    assert row["meta_dir"] == "/var/lib/influxdb2/influxd.bolt"
    assert row["max_concurrent_queries"] == "10"
    assert calls[1][0] == "https://influx.local:8443/api/v2/config"
    assert calls[1][1]["headers"] == {"Authorization": "Token operator-secret"}
    assert calls[1][1]["verify"] is False


@pytest.mark.asyncio
async def test_invalid_operator_token_keeps_basics_and_emits_failed_marker(monkeypatch):
    def fake_get(url, **kwargs):
        if url.endswith("/health"):
            return FakeResponse(body={"status": "pass", "version": "2.7.5"})
        return FakeResponse(status_code=403)

    monkeypatch.setattr("plugins.inputs.influxdb.influxdb_info.requests.get", fake_get)

    result = await InfluxdbInfo(
        {"host": "influx.local", "token": "must-not-leak"}
    ).list_all_resources()

    rows = result["result"]["influxdb"]
    assert rows[0]["version"] == "2.7.5"
    assert rows[1] == {
        "ip_addr": "influx.local",
        "port": 8086,
        "collect_status": "failed",
        "collect_error": "Operator Token 无效或权限不足，无法读取 InfluxDB 运行配置",
    }
    assert "must-not-leak" not in str(result)


@pytest.mark.asyncio
async def test_v1_uses_ping_for_basic_identification(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/health"):
            return FakeResponse(status_code=404)
        return FakeResponse(headers={"X-Influxdb-Version": "1.8.10"})

    monkeypatch.setattr("plugins.inputs.influxdb.influxdb_info.requests.get", fake_get)

    result = await InfluxdbInfo({"host": "influx-v1.local"}).list_all_resources()

    assert result["result"]["influxdb"][0]["version"] == "1.8.10"
    assert calls == [
        "http://influx-v1.local:8086/health",
        "http://influx-v1.local:8086/ping",
    ]


@pytest.mark.asyncio
async def test_unreachable_instance_is_reported_as_collection_failure(monkeypatch):
    def fake_get(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("plugins.inputs.influxdb.influxdb_info.requests.get", fake_get)

    result = await InfluxdbInfo(
        {"host": "influx.local", "token": "must-not-leak"}
    ).list_all_resources()

    assert result["success"] is False
    assert "cmdb_collect_error" in result["result"]
    assert "must-not-leak" not in str(result)


def test_collection_service_preserves_plugin_failure_marker():
    service = CollectionService.__new__(CollectionService)
    service.host = "influx.local"
    service.model_id = "influxdb"

    processed = service._process_result(
        {
            "success": True,
            "result": {
                "influxdb": [
                    {"version": "2.7.5"},
                    {
                        "collect_status": "failed",
                        "collect_error": "Operator Token 无效或权限不足",
                    },
                ]
            },
        }
    )

    assert processed["influxdb"][0]["collect_status"] == "success"
    assert processed["influxdb"][1]["collect_status"] == "failed"
