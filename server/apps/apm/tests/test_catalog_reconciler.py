from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore, TelemetryStoreUnavailable
from apps.apm.models import ApmServiceInstance
from apps.apm.services import DjangoTelemetryCatalogService, TelemetryCatalogReconciler
from apps.apm.services.contracts import CatalogDiscovery, InstanceActivity
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _activity(application_id, instance_id, seen_at, *, service_name="checkout", environment="production", version="1.2.3"):
    return InstanceActivity(
        service_namespace=application_id,
        service_name=service_name,
        instance_id=instance_id,
        environment=environment,
        version=version,
        last_seen_at=seen_at,
    )


def test_reconciler_keeps_instances_distinct_and_reports_missing_identity():
    observed_at = timezone.now()
    create_application("shop", (10, 20))
    metric_store = InMemoryMetricStore(
        activities=[
            _activity("shop", "pod-a", observed_at - timedelta(minutes=2)),
            _activity("shop", "pod-b", observed_at - timedelta(minutes=1)),
            _activity("shop", None, observed_at),
        ]
    )

    result = TelemetryCatalogReconciler(metric_store).reconcile(observed_at=observed_at)

    assert result.discovered_services == 1
    assert result.discovered_instances == 2
    assert result.missing_instance_identities == 1
    assert set(ApmServiceInstance.objects.values_list("instance_id", flat=True)) == {"pod-a", "pod-b"}


def test_missing_instance_identity_still_counts_the_discovered_service():
    observed_at = timezone.now()
    create_application("shop", (10,))

    result = TelemetryCatalogReconciler(InMemoryMetricStore(activities=[_activity("shop", None, observed_at)])).reconcile(observed_at=observed_at)

    assert result.discovered_services == 1
    assert result.discovered_instances == 0
    assert result.missing_instance_identities == 1


@pytest.mark.parametrize(
    "invalid_activity",
    [
        _activity("n" * 257, "pod-bad", timezone.now()),
        _activity("shop", "pod-bad", timezone.now(), service_name="  "),
        _activity("shop", "pod-bad", timezone.now(), service_name="s" * 257),
        _activity("shop", "i" * 513, timezone.now()),
        _activity("shop", "pod-bad", timezone.now(), environment="e" * 257),
        _activity("shop", "pod-bad", timezone.now(), version="v" * 257),
    ],
)
def test_invalid_catalog_identity_is_isolated_from_valid_activity(invalid_activity):
    observed_at = timezone.now()
    create_application("shop", (10,))
    metric_store = InMemoryMetricStore(
        activities=[
            _activity("shop", "pod-a", observed_at - timedelta(minutes=1)),
            invalid_activity,
            _activity("shop", "pod-c", observed_at),
        ]
    )

    result = TelemetryCatalogReconciler(metric_store).reconcile(observed_at=observed_at)

    assert result.invalid_activities == 1
    assert result.discovered_services == 1
    assert result.discovered_instances == 2
    assert set(ApmServiceInstance.objects.values_list("instance_id", flat=True)) == {"pod-a", "pod-c"}


def test_invalid_catalog_diagnostics_are_sampled_without_logging_identity_values(caplog):
    observed_at = timezone.now()
    create_application("shop", (10,))
    marker = "identity-must-not-appear-in-logs"
    activities = [_activity("shop", f"{marker}-{index}-" + "x" * 512, observed_at) for index in range(25)]

    result = TelemetryCatalogReconciler(InMemoryMetricStore(activities=activities)).reconcile(observed_at=observed_at)

    assert result.invalid_activities == 25
    record = next(record for record in caplog.records if record.message == "APM telemetry ignored invalid catalog identities")
    assert len(record.invalid_identity_samples) == 20
    assert marker not in caplog.text


def test_reconciler_skips_metrics_for_unknown_applications():
    observed_at = timezone.now()
    create_application("shop", (10,))
    metric_store = InMemoryMetricStore(
        activities=[
            _activity("unknown", "stale-pod", observed_at - timedelta(minutes=1)),
            _activity("shop", "live-pod", observed_at),
        ]
    )

    result = TelemetryCatalogReconciler(metric_store).reconcile(observed_at=observed_at)

    assert result.discovered_services == 1
    assert result.discovered_instances == 1
    assert result.unknown_applications == 1
    assert list(ApmServiceInstance.objects.values_list("instance_id", flat=True)) == ["live-pod"]


def test_reconciler_does_not_archive_when_victoria_traces_query_fails(mocker):
    store = mocker.Mock()
    store.instance_activity.side_effect = TelemetryStoreUnavailable("VictoriaTraces unavailable")
    catalog = mocker.Mock()

    with pytest.raises(TelemetryStoreUnavailable):
        TelemetryCatalogReconciler(store, catalog).reconcile(observed_at=timezone.now())

    catalog.discover.assert_not_called()
    catalog.archive_stale.assert_not_called()


def test_stale_instances_archive_and_new_activity_unarchives_history():
    observed_at = timezone.now()
    create_application("shop", (10,))
    metric_store = InMemoryMetricStore(activities=[_activity("shop", "pod-old", observed_at - timedelta(days=8))])
    reconciler = TelemetryCatalogReconciler(metric_store)
    reconciler.reconcile(observed_at=observed_at - timedelta(days=8))

    archived = reconciler.reconcile(observed_at=observed_at)
    instance = ApmServiceInstance.objects.get(instance_id="pod-old")
    assert archived.archived_instances == archived.archived_services == 1
    assert instance.archived_at == observed_at

    metric_store.add_activity(_activity("shop", "pod-old", observed_at + timedelta(minutes=1)))
    reconciler.reconcile(observed_at=observed_at + timedelta(minutes=1))
    instance.refresh_from_db()
    instance.service.refresh_from_db()
    assert instance.archived_at is None
    assert instance.service.archived_at is None
    assert ApmServiceInstance.objects.count() == 1


def test_manual_archives_survive_new_activity():
    observed_at = timezone.now()
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    discovered = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-manual", "production", seen_at=observed_at))
    catalog.archive_service(discovered.service.id, reason="manual", actor="tester")
    catalog.archive_instance(discovered.instance.id, reason="manual", actor="tester")

    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-manual", "production", seen_at=observed_at + timedelta(minutes=1)))
    discovered.service.refresh_from_db()
    discovered.instance.refresh_from_db()
    assert discovered.service.archive_reason == discovered.instance.archive_reason == "manual"


def test_environment_views_and_instance_status_filters_are_bounded(apm_api_client):
    now = timezone.now()
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-test", "testing", seen_at=now - timedelta(hours=1)))
    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-prod", "production", seen_at=now))

    services = apm_api_client.get("/api/v1/apm/services/")
    active = apm_api_client.get("/api/v1/apm/instances/?status=active")
    silent = apm_api_client.get("/api/v1/apm/instances/?status=silent")

    assert [(item["environment"], item["status"]) for item in services.data[0]["environment_views"]] == [
        ("production", "active"),
        ("testing", "silent"),
    ]
    assert [item["instance_id"] for item in active.data] == ["pod-prod"]
    assert [item["instance_id"] for item in silent.data] == ["pod-test"]
