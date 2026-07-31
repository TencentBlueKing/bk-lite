from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.models import (
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoIngestSourceService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery


pytestmark = pytest.mark.django_db


def _create_source(name: str, organizations: list[int]):
    return DjangoIngestSourceService().create(
        name=name,
        ingest_type="otlp_http",
        organization_ids=organizations,
        actor="tester",
    ).source


def test_service_and_instance_identity_are_distinct_and_normalized():
    source_a = _create_source("source-a", [10])
    source_b = _create_source("source-b", [20])
    catalog = DjangoTelemetryCatalogService()
    started_at = timezone.now()

    first = catalog.discover(
        CatalogDiscovery(
            ingest_source_id=source_a.id,
            service_namespace=None,
            service_name=" checkout ",
            instance_id="pod-a",
            environment="prod",
            seen_at=started_at,
        )
    )
    second = catalog.discover(
        CatalogDiscovery(
            ingest_source_id=source_b.id,
            service_namespace="",
            service_name="checkout",
            instance_id="pod-b",
            environment="staging",
            seen_at=started_at + timedelta(minutes=1),
        )
    )

    assert first.service == second.service
    assert first.instance != second.instance
    assert ApmService.objects.count() == 1
    assert ApmServiceInstance.objects.count() == 2
    assert first.service.normalized_namespace == ""
    assert first.service.name == " checkout "


def test_missing_instance_identity_does_not_create_fake_catalog_rows():
    source = _create_source("source", [10])

    result = DjangoTelemetryCatalogService().discover(
        CatalogDiscovery(
            ingest_source_id=source.id,
            service_namespace="shop",
            service_name="checkout",
            instance_id=None,
            environment="prod",
        )
    )

    assert result.missing_instance_identity is True
    assert result.instance is None
    assert ApmServiceInstance.objects.count() == 0
    assert ApmService.objects.count() == 0
    source.refresh_from_db()
    assert source.last_missing_instance_identity_at is not None


def test_first_instance_defines_service_organizations_and_later_changes_do_not_leak():
    ingest_service = DjangoIngestSourceService()
    source = ingest_service.create(
        name="source",
        ingest_type="otlp_http",
        organization_ids=[10, 20],
        actor="tester",
    ).source
    catalog = DjangoTelemetryCatalogService()

    first = catalog.discover(
        CatalogDiscovery(
            ingest_source_id=source.id,
            service_namespace="shop",
            service_name="checkout",
            instance_id="pod-a",
            environment="prod",
        )
    )
    ingest_service.set_organizations(source.id, [30], actor="tester")
    second = catalog.discover(
        CatalogDiscovery(
            ingest_source_id=source.id,
            service_namespace="shop",
            service_name="checkout",
            instance_id="pod-b",
            environment="prod",
        )
    )

    assert set(
        ApmServiceInstanceOrganization.objects.filter(instance=first.instance).values_list(
            "organization",
            flat=True,
        )
    ) == {30}
    assert set(
        ApmServiceInstanceOrganization.objects.filter(instance=second.instance).values_list(
            "organization",
            flat=True,
        )
    ) == {30}
    assert set(
        ApmServiceOrganization.objects.filter(service=first.service).values_list(
            "organization",
            flat=True,
        )
    ) == {10, 20}


def test_custom_instance_organizations_stop_following_source_defaults():
    ingest_service = DjangoIngestSourceService()
    source = ingest_service.create(
        name="source",
        ingest_type="otlp_http",
        organization_ids=[10],
        actor="tester",
    ).source
    catalog = DjangoTelemetryCatalogService()
    result = catalog.discover(
        CatalogDiscovery(
            ingest_source_id=source.id,
            service_namespace="shop",
            service_name="checkout",
            instance_id="pod-a",
            environment="prod",
        )
    )

    catalog.set_instance_organizations(result.instance.id, [20], actor="tester")
    ingest_service.set_organizations(source.id, [30], actor="tester")

    result.instance.refresh_from_db()
    assert result.instance.permission_mode == ApmServiceInstance.PermissionMode.CUSTOM
    assert set(result.instance.organization_links.values_list("organization", flat=True)) == {20}


def test_latest_source_handoff_updates_inherited_permissions_but_stale_observations_do_not_regress():
    now = timezone.now()
    source_a = _create_source("source-a", [10])
    source_b = _create_source("source-b", [20])
    catalog = DjangoTelemetryCatalogService()
    first = catalog.discover(
        CatalogDiscovery(source_a.id, "shop", "checkout", "pod-a", "testing", seen_at=now)
    )

    catalog.discover(
        CatalogDiscovery(
            source_b.id,
            "shop",
            "checkout",
            "pod-a",
            "production",
            version="2.0",
            seen_at=now + timedelta(minutes=1),
        )
    )
    catalog.discover(
        CatalogDiscovery(
            source_a.id,
            "shop",
            "checkout",
            "pod-a",
            "stale-environment",
            version="1.0",
            seen_at=now - timedelta(minutes=1),
        )
    )

    first.instance.refresh_from_db()
    assert first.instance.ingest_source == source_b
    assert first.instance.environment == "production"
    assert first.instance.version == "2.0"
    assert first.instance.last_seen_at == now + timedelta(minutes=1)
    assert set(first.instance.organization_links.values_list("organization", flat=True)) == {20}
