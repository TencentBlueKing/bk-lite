from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore
from apps.apm.models import ApmService, ApmServiceInstance
from apps.apm.services import DjangoIngestSourceService, DjangoTelemetryCatalogService, TelemetryCatalogReconciler
from apps.apm.services.contracts import CatalogDiscovery, InstanceActivity


pytestmark = pytest.mark.django_db


def _source(organizations=(10, 20)):
    return DjangoIngestSourceService().create(
        name="runtime-source",
        ingest_type="otlp_http",
        organization_ids=organizations,
        actor="tester",
    ).source


def _activity(source_id, instance_id, seen_at, *, environment="production"):
    return InstanceActivity(
        service_namespace="shop",
        service_name="checkout",
        instance_id=instance_id,
        environment=environment,
        version="1.2.3",
        ingest_source_id=source_id,
        last_seen_at=seen_at,
    )


def test_reconciler_keeps_pod_instances_distinct_and_reports_missing_identity(apm_api_client):
    observed_at = timezone.now()
    source = _source()
    metric_store = InMemoryMetricStore(
        activities=[
            _activity(source.id, "pod-a", observed_at - timedelta(minutes=2)),
            _activity(source.id, "pod-b", observed_at - timedelta(minutes=1)),
            _activity(source.id, None, observed_at),
        ]
    )

    result = TelemetryCatalogReconciler(metric_store).reconcile(observed_at=observed_at)

    assert result.discovered_services == 1
    assert result.discovered_instances == 2
    assert result.missing_instance_identities == 1
    assert ApmService.objects.count() == 1
    assert set(ApmServiceInstance.objects.values_list("instance_id", flat=True)) == {"pod-a", "pod-b"}
    source.refresh_from_db()
    assert source.first_received_at == observed_at - timedelta(minutes=2)
    assert source.last_received_at == observed_at
    sources = apm_api_client.get("/api/v1/apm/ingest-sources/")
    assert sources.data[0]["missing_instance_identity"] is True


def test_stale_instances_archive_and_new_activity_unarchives_without_replacing_history():
    observed_at = timezone.now()
    source = _source((10,))
    metric_store = InMemoryMetricStore(
        activities=[_activity(source.id, "pod-old", observed_at - timedelta(days=8))]
    )
    reconciler = TelemetryCatalogReconciler(metric_store)
    reconciler.reconcile(observed_at=observed_at - timedelta(days=8))

    archived = reconciler.reconcile(observed_at=observed_at)
    instance = ApmServiceInstance.objects.get(instance_id="pod-old")
    instance.refresh_from_db()
    assert archived.archived_instances == 1
    assert archived.archived_services == 1
    assert instance.archived_at == observed_at

    metric_store.add_activity(_activity(source.id, "pod-old", observed_at + timedelta(minutes=1)))
    restored = reconciler.reconcile(observed_at=observed_at + timedelta(minutes=1))

    instance.refresh_from_db()
    instance.service.refresh_from_db()
    assert restored.discovered_instances == 1
    assert instance.archived_at is None
    assert instance.service.archived_at is None
    assert ApmServiceInstance.objects.count() == 1


def test_manual_archives_survive_new_activity_until_explicit_restore():
    observed_at = timezone.now()
    source = _source((10,))
    catalog = DjangoTelemetryCatalogService()
    discovered = catalog.discover(
        CatalogDiscovery(source.id, "shop", "checkout", "pod-manual", "production", seen_at=observed_at)
    )
    catalog.archive_service(discovered.service.id, reason="manual", actor="tester")
    catalog.archive_instance(discovered.instance.id, reason="manual", actor="tester")

    catalog.discover(
        CatalogDiscovery(
            source.id,
            "shop",
            "checkout",
            "pod-manual",
            "production",
            seen_at=observed_at + timedelta(minutes=1),
        )
    )

    discovered.service.refresh_from_db()
    discovered.instance.refresh_from_db()
    assert discovered.service.archive_reason == "manual"
    assert discovered.service.archived_at is not None
    assert discovered.instance.archive_reason == "manual"
    assert discovered.instance.archived_at is not None


def test_environment_views_are_separate_and_instance_status_filters_are_bounded(apm_api_client):
    now = timezone.now()
    source = _source((10,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(
        CatalogDiscovery(source.id, "shop", "checkout", "pod-test", "testing", seen_at=now - timedelta(hours=1))
    )
    catalog.discover(
        CatalogDiscovery(source.id, "shop", "checkout", "pod-prod", "production", seen_at=now)
    )

    services = apm_api_client.get("/api/v1/apm/services/")
    active = apm_api_client.get("/api/v1/apm/instances/?status=active")
    silent = apm_api_client.get("/api/v1/apm/instances/?status=silent")

    assert services.status_code == 200
    environment_views = services.data[0]["environment_views"]
    assert [(item["environment"], item["status"]) for item in environment_views] == [
        ("production", "active"),
        ("testing", "silent"),
    ]
    assert environment_views[0]["last_seen_at"] == now
    assert environment_views[1]["last_seen_at"] == now - timedelta(hours=1)
    assert [item["instance_id"] for item in active.data] == ["pod-prod"]
    assert [item["instance_id"] for item in silent.data] == ["pod-test"]


def test_archived_instances_are_hidden_by_default_and_can_be_restored(apm_api_client):
    now = timezone.now()
    source = _source((10,))
    catalog = DjangoTelemetryCatalogService()
    discovered = catalog.discover(
        CatalogDiscovery(source.id, "shop", "checkout", "pod-old", "production", seen_at=now - timedelta(days=8))
    )
    catalog.archive_stale(observed_at=now)

    default_list = apm_api_client.get("/api/v1/apm/instances/")
    archived_list = apm_api_client.get("/api/v1/apm/instances/?status=archived")
    restored = apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/restore/")

    assert default_list.data == []
    assert [item["instance_id"] for item in archived_list.data] == ["pod-old"]
    assert restored.status_code == 200
    assert restored.data["status"] == "silent"
