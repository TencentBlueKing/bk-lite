from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.adapters import InMemoryMetricStore
from apps.apm.models import ApmApplication, ApmService, ApmServiceInstance
from apps.apm.services.contracts import InstanceActivity
from apps.apm.services.health import CATALOG_RECONCILE_HEALTH_KEY
from apps.apm.services.probe_artifacts import PYTHON_WHEELS_ARTIFACT_NAME
from apps.apm.tasks import reconcile_telemetry_catalog

pytestmark = pytest.mark.django_db


@pytest.fixture
def real_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "apm-ingest-chain-test",
        }
    }
    from django.core.cache import cache

    cache.clear()
    yield cache
    cache.clear()


def _region(monkeypatch):
    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = "apm-east.example.com"
    region.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "http://10.10.10.1:8011"}
    monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
    return region


def _activity(seen_at, *, service_name="checkout", instance_id="pod-checkout-1"):
    return InstanceActivity(
        service_namespace="shop",
        service_name=service_name,
        instance_id=instance_id,
        environment="production",
        version="1.4.0",
        last_seen_at=seen_at,
        language="python",
    )


def test_application_probe_report_reconcile_puts_service_and_instance_in_catalog(
    apm_api_client,
    monkeypatch,
    mocker,
    real_cache,
):
    _region(monkeypatch)
    monkeypatch.setattr(
        "apps.apm.views.open_probe.open_probe_artifact_stream",
        lambda artifact_name: (iter([b"wheel-bytes"]), artifact_name),
    )
    seen_at = timezone.now() - timedelta(minutes=1)
    mocker.patch(
        "apps.apm.tasks.VictoriaTracesTelemetryStore",
        return_value=InMemoryMetricStore(activities=[_activity(seen_at)]),
    )

    created = apm_api_client.post(
        "/api/v1/apm/applications/",
        {
            "application_id": "shop",
            "name": "电商主站",
            "organization_ids": [10],
        },
        format="json",
    )
    snippet = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": "python",
            "runtime": "host",
            "service_name": "checkout",
            "service_version": "1.4.0",
            "environment": "production",
        },
        format="json",
    )
    probe = APIClient().get(f"/api/v1/apm/open_api/probe/download/{PYTHON_WHEELS_ARTIFACT_NAME}")
    reconcile = reconcile_telemetry_catalog.run()
    services = apm_api_client.get("/api/v1/apm/services/")
    instances = apm_api_client.get("/api/v1/apm/instances/")
    health = apm_api_client.get("/api/v1/apm/health/")

    assert created.status_code == 201
    assert snippet.status_code == 200
    assert snippet.data["application_id"] == "shop"
    assert "service.namespace=shop" in snippet.data["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.name=checkout" in snippet.data["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
    assert f"/api/v1/apm/open_api/probe/download/{PYTHON_WHEELS_ARTIFACT_NAME}" in snippet.data["code"]
    assert probe.status_code == 200
    assert b"".join(probe.streaming_content) == b"wheel-bytes"
    assert reconcile["discovered_services"] == 1
    assert reconcile["discovered_instances"] == 1
    assert [item["name"] for item in services.data] == ["checkout"]
    assert [item["instance_id"] for item in instances.data] == ["pod-checkout-1"]
    assert ApmApplication.objects.filter(application_id="shop", is_builtin=False).exists()
    assert ApmService.objects.filter(name="checkout").exists()
    assert ApmServiceInstance.objects.filter(instance_id="pod-checkout-1").exists()
    assert health.status_code == 200
    assert health.data["catalog_reconcile"]["status"] == "ok"
    assert real_cache.get(CATALOG_RECONCILE_HEALTH_KEY)["status"] == "ok"


def test_catalog_reconcile_does_not_materialize_unknown_or_empty_namespace_reports(
    apm_api_client,
    mocker,
):
    apm_api_client.post(
        "/api/v1/apm/applications/",
        {"application_id": "shop", "name": "电商主站", "organization_ids": [10]},
        format="json",
    )
    seen_at = timezone.now() - timedelta(minutes=1)
    mocker.patch(
        "apps.apm.tasks.VictoriaTracesTelemetryStore",
        return_value=InMemoryMetricStore(
            activities=[
                _activity(seen_at),
                InstanceActivity("", "kernel-worker", "node-a", "production", "1.0", seen_at),
                InstanceActivity("unknown", "billing", "pod-hidden", "production", "1.0", seen_at),
            ]
        ),
    )

    result = reconcile_telemetry_catalog.run()
    services = apm_api_client.get("/api/v1/apm/services/")
    instances = apm_api_client.get("/api/v1/apm/instances/")

    assert result["discovered_services"] == 1
    assert result["discovered_instances"] == 1
    assert result["unknown_applications"] == 2
    assert [item["name"] for item in services.data] == ["checkout"]
    assert [item["instance_id"] for item in instances.data] == ["pod-checkout-1"]
    assert not ApmService.objects.filter(name__in=["kernel-worker", "billing"]).exists()
