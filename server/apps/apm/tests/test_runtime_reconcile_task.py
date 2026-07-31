import pytest

from apps.apm.config import CELERY_BEAT_SCHEDULE
from apps.apm.services.contracts import CatalogReconcileResult
from apps.apm.tasks import probe_apm_runtime_dependencies, reconcile_telemetry_catalog
from apps.apm.services.health import CATALOG_RECONCILE_HEALTH_KEY, RuntimeDependencyHealthProbe


pytestmark = pytest.mark.django_db


@pytest.fixture
def real_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "apm-reconcile-health-test",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield cache
    cache.clear()


def test_catalog_reconcile_is_a_runtime_beat_task_and_not_batch_init():
    schedule = CELERY_BEAT_SCHEDULE["apm_reconcile_telemetry_catalog"]

    assert schedule["task"] == "apps.apm.tasks.reconcile_telemetry_catalog"
    assert reconcile_telemetry_catalog.retry_kwargs["max_retries"] == 5
    assert reconcile_telemetry_catalog.retry_backoff_max == 300
    with open("apps/core/management/commands/batch_init.py", encoding="utf-8") as file:
        batch_init = file.read()
        assert "reconcile_telemetry_catalog" not in batch_init
        assert "probe_apm_runtime_dependencies" not in batch_init
    assert CELERY_BEAT_SCHEDULE["apm_probe_runtime_dependencies"]["task"] == (
        "apps.apm.tasks.probe_apm_runtime_dependencies"
    )


def test_runtime_task_returns_reconcile_health_without_startup_side_effects(mocker):
    mocker.patch("apps.apm.tasks.cache.add", return_value=True)
    delete = mocker.patch("apps.apm.tasks.cache.delete")
    set_health = mocker.patch("apps.apm.tasks.cache.set")
    reconcile = mocker.patch(
        "apps.apm.tasks.TelemetryCatalogReconciler.reconcile",
        return_value=CatalogReconcileResult(2, 3, 1, 4, 5),
    )

    result = reconcile_telemetry_catalog.run()

    assert result == {
        "discovered_services": 2,
        "discovered_instances": 3,
        "missing_instance_identities": 1,
        "archived_services": 4,
        "archived_instances": 5,
    }
    reconcile.assert_called_once()
    delete.assert_called_once()
    assert set_health.call_args.args[0] == CATALOG_RECONCILE_HEALTH_KEY
    assert set_health.call_args.args[1]["status"] == "ok"


def test_health_endpoint_exposes_reconcile_degradation_without_storage_details(apm_api_client, real_cache):
    real_cache.set(
        CATALOG_RECONCILE_HEALTH_KEY,
        {"status": "degraded", "last_failed_at": "2026-07-30T10:00:00+00:00"},
        timeout=None,
    )

    response = apm_api_client.get("/api/v1/apm/health/")

    assert response.status_code == 200
    assert response.data["catalog_reconcile"] == {
        "status": "degraded",
        "last_failed_at": "2026-07-30T10:00:00+00:00",
    }
    assert response.data["collector"]["status"] == "pending"
    assert response.data["trace_store"]["status"] == "pending"
    assert response.data["metric_store"]["status"] == "pending"
    assert response.data["policy_evaluation"]["status"] == "pending"
    assert response.data["notification_delivery"]["status"] == "pending"


class FakeResponse:
    def __init__(self, healthy=True):
        self.healthy = healthy

    def raise_for_status(self):
        if not self.healthy:
            import requests

            raise requests.HTTPError("unavailable")


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, endpoint, auth, timeout):
        self.calls.append((endpoint, auth, timeout))
        return FakeResponse(healthy="traces" not in endpoint)


def test_runtime_dependency_probe_is_bounded_and_hides_endpoints(monkeypatch):
    monkeypatch.setenv("APM_COLLECTOR_HEALTH_ENDPOINT", "http://collector:13133/")
    monkeypatch.setenv("APM_VICTORIATRACES_HEALTH_ENDPOINT", "http://traces:10428/health")
    monkeypatch.setenv("APM_VICTORIAMETRICS_HEALTH_ENDPOINT", "http://metrics:8428/health")
    session = FakeSession()

    result = RuntimeDependencyHealthProbe(session=session).probe()

    assert result["collector"]["status"] == "ok"
    assert result["trace_store"]["status"] == "degraded"
    assert result["trace_store"]["error_code"] == "trace_store_unavailable"
    assert result["metric_store"]["status"] == "ok"
    assert all(call[2] == (1, 2) for call in session.calls)
    assert "endpoint" not in str(result)


def test_runtime_dependency_probe_task_only_updates_runtime_cache(mocker):
    result = {"collector": {"status": "ok"}}
    mocker.patch("apps.apm.tasks.RuntimeDependencyHealthProbe.probe", return_value=result)
    set_health = mocker.patch("apps.apm.tasks.cache.set")

    assert probe_apm_runtime_dependencies.run() == result
    assert set_health.call_args.args[1] == result
    assert set_health.call_args.kwargs["timeout"] is None
