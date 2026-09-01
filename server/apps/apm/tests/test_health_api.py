import pytest
from rest_framework.test import APIClient

from apps.apm.services.health import HEALTH_COMPONENT_KEYS, RUNTIME_COMPONENTS, RuntimeDependencyHealthProbe
from apps.apm.tasks import probe_apm_runtime_dependencies

pytestmark = pytest.mark.django_db


@pytest.fixture
def real_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "apm-health-http-test",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield cache
    cache.clear()


class FakeResponse:
    def __init__(self, healthy=True, *, text="", payload=None):
        self.healthy = healthy
        self.text = text
        self.payload = payload or {}

    def raise_for_status(self):
        if not self.healthy:
            import requests

            raise requests.HTTPError("unavailable")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, *, traces_healthy=True, jetstream_bytes=100):
        self.traces_healthy = traces_healthy
        self.jetstream_bytes = jetstream_bytes
        self.calls = []

    def get(self, endpoint, auth, timeout, params=None):
        self.calls.append((endpoint, auth, timeout, params))
        if endpoint.endswith("/metrics"):
            return FakeResponse(
                text=(
                    "bklite_apm_nats_publish_acks_total 12\n"
                    'otelcol_exporter_queue_size{exporter="nats_jetstream"} 10\n'
                    'otelcol_exporter_queue_capacity{exporter="nats_jetstream"} 100\n'
                )
            )
        if endpoint.endswith("/jsz"):
            return FakeResponse(
                payload={
                    "account_details": [
                        {
                            "stream_detail": [
                                {
                                    "name": "APM_TRACES",
                                    "state": {"bytes": self.jetstream_bytes, "messages": 2},
                                    "consumer_detail": [
                                        {
                                            "name": "BKLITE_APM_SYSTEM",
                                            "num_pending": 2,
                                            "num_ack_pending": 1,
                                            "num_redelivered": 3,
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            )
        if "traces" in endpoint:
            return FakeResponse(healthy=self.traces_healthy)
        return FakeResponse()


def _configure_probe_endpoints(monkeypatch):
    monkeypatch.setenv("APM_REGIONAL_COLLECTOR_HEALTH_ENDPOINT", "http://regional:13133/")
    monkeypatch.setenv("APM_REGIONAL_COLLECTOR_METRICS_ENDPOINT", "http://regional:8888/metrics")
    monkeypatch.setenv("APM_NATS_MONITOR_ENDPOINT", "http://nats:8222")
    monkeypatch.setenv("APM_SYSTEM_COLLECTOR_HEALTH_ENDPOINT", "http://system:13133/")
    monkeypatch.setenv("APM_VICTORIATRACES_HEALTH_ENDPOINT", "http://traces:10428/health")


def test_health_http_exposes_collector_nats_jetstream_vt_and_retention(apm_api_client, real_cache, monkeypatch, mocker):
    _configure_probe_endpoints(monkeypatch)
    mocker.patch(
        "apps.apm.tasks.RuntimeDependencyHealthProbe",
        return_value=RuntimeDependencyHealthProbe(session=FakeSession(traces_healthy=False)),
    )

    probe_apm_runtime_dependencies.run()
    response = apm_api_client.get("/api/v1/apm/health/")

    assert response.status_code == 200
    assert response.data["regional_collector"]["status"] == "ok"
    assert response.data["system_collector"]["status"] == "ok"
    assert response.data["nats_publish"]["status"] == "ok"
    assert response.data["nats_publish"]["publish_acks"] == 12
    assert response.data["jetstream"]["status"] == "ok"
    assert response.data["jetstream"]["stream_messages"] == 2
    assert response.data["victoria_traces"]["status"] == "degraded"
    assert response.data["victoria_traces"]["error_code"] == "victoria_traces_unavailable"
    assert response.data["victoria_traces_retention"]["status"] == "ok"
    assert response.data["victoria_traces_retention"]["configured_days"] == 35
    assert "endpoint" not in str(response.data)
    for component in (*RUNTIME_COMPONENTS, *HEALTH_COMPONENT_KEYS):
        assert component in response.data


def test_health_http_exposes_degraded_retention_and_jetstream_capacity(
    apm_api_client,
    real_cache,
    monkeypatch,
    mocker,
):
    _configure_probe_endpoints(monkeypatch)
    monkeypatch.setenv("APM_TRACE_RETENTION", "30d")
    monkeypatch.setenv("APM_NATS_STREAM_MAX_BYTES", "100")
    mocker.patch(
        "apps.apm.tasks.RuntimeDependencyHealthProbe",
        return_value=RuntimeDependencyHealthProbe(
            session=FakeSession(jetstream_bytes=90),
        ),
    )

    probe_apm_runtime_dependencies.run()
    response = apm_api_client.get("/api/v1/apm/health/")

    assert response.status_code == 200
    assert response.data["victoria_traces_retention"]["status"] == "degraded"
    assert response.data["victoria_traces_retention"]["error_code"] == "victoria_traces_retention_too_short"
    assert response.data["jetstream"]["status"] == "degraded"
    assert response.data["jetstream"]["error_code"] == "jetstream_capacity_critical"


def test_health_http_stays_pending_when_runtime_cache_is_empty(apm_api_client, real_cache):
    response = apm_api_client.get("/api/v1/apm/health/")

    assert response.status_code == 200
    for component in RUNTIME_COMPONENTS:
        assert response.data[component] == {"status": "pending"}
    for component in HEALTH_COMPONENT_KEYS:
        assert response.data[component] == {"status": "pending"}


def test_health_http_requires_directory_permission(apm_user_without_permissions):
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/health/")

    assert response.status_code == 403
