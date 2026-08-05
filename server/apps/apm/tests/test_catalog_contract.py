from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.models import ApmApplication, ApmApplicationOrganization, ApmService, ApmServiceInstance, ApmServiceOrganization
from apps.apm.services import DjangoApmApplicationService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def test_service_and_instance_are_discovered_under_a_known_application():
    application = create_application("shop", (10, 20))

    result = DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", " checkout ", "pod-a", "production", version="1.2.3"))

    assert result.service.application == application
    assert result.service.normalized_namespace == "shop"
    assert result.instance.service == result.service
    assert result.instance.version == "1.2.3"
    assert set(result.service.organization_links.values_list("organization", flat=True)) == {10, 20}
    assert set(result.instance.organization_links.values_list("organization", flat=True)) == {10, 20}


def test_unknown_application_cannot_create_catalog_rows():
    catalog = DjangoTelemetryCatalogService()

    with pytest.raises(ApmApplication.DoesNotExist):
        catalog.discover(CatalogDiscovery("unknown", "checkout", "pod-a", "prod"))

    assert ApmService.objects.count() == 0
    assert ApmServiceInstance.objects.count() == 0


def test_empty_namespace_is_discovered_under_builtin_application():
    application = ApmApplication.objects.get(application_id="", is_builtin=True)
    ApmApplicationOrganization.objects.create(application=application, organization=10)

    result = DjangoTelemetryCatalogService().discover(CatalogDiscovery("", "kernel-worker", "node-a", "prod"))

    assert result.service.application == application
    assert result.service.namespace == ""
    assert set(result.service.organization_links.values_list("organization", flat=True)) == {10}


def test_builtin_application_tracks_the_current_application_organization_union():
    shop = create_application("shop", (10,))
    create_application("billing", (20,))
    uncategorized = DjangoTelemetryCatalogService().discover(CatalogDiscovery("", "kernel-worker", "node-a", "prod")).service

    DjangoApmApplicationService().update(
        shop.id,
        name=shop.name,
        description="",
        organization_ids=[30],
        actor="tester",
    )

    builtin = ApmApplication.objects.get(is_builtin=True)
    assert set(builtin.organization_links.values_list("organization", flat=True)) == {20, 30}
    assert set(uncategorized.organization_links.values_list("organization", flat=True)) == {20, 30}


def test_missing_instance_identity_discovers_service_without_fake_instance():
    create_application("shop", (10,))

    result = DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", "checkout", None, "prod"))

    assert result.missing_instance_identity is True
    assert result.service is not None
    assert result.instance is None
    assert ApmServiceInstance.objects.count() == 0


def test_catalog_accepts_identity_values_at_the_persistence_limits_without_truncation():
    create_application("shop", (10,))
    discovery = CatalogDiscovery(
        "shop",
        "服" * 256,
        "实" * 512,
        "环" * 256,
        version="版" * 256,
    )

    result = DjangoTelemetryCatalogService().discover(discovery)

    assert result.service.name == discovery.service_name
    assert result.instance.instance_id == discovery.instance_id
    assert result.instance.environment == discovery.environment
    assert result.instance.version == discovery.version


def test_application_organization_changes_sync_services_and_only_inherited_instances():
    application = create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    inherited = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "prod")).instance
    custom = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-b", "prod")).instance
    catalog.set_instance_organizations(custom.id, [20], actor="tester")

    DjangoApmApplicationService().update(
        application.id,
        name=application.name,
        description="",
        organization_ids=[30],
        actor="tester",
    )
    custom.refresh_from_db()
    inherited.service.refresh_from_db()

    assert set(inherited.service.organization_links.values_list("organization", flat=True)) == {30}
    assert set(inherited.organization_links.values_list("organization", flat=True)) == {30}
    assert set(custom.organization_links.values_list("organization", flat=True)) == {20}
    assert custom.permission_mode == ApmServiceInstance.PermissionMode.CUSTOM


def test_application_organization_sync_rolls_back_all_catalog_levels(mocker):
    application = create_application("shop", (10,))
    original_name = application.name
    discovered = DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", "checkout", "pod-a", "prod"))
    mocker.patch(
        "apps.apm.services.applications.ApmServiceInstanceOrganization.objects.bulk_create",
        side_effect=RuntimeError("injected failure"),
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        DjangoApmApplicationService().update(
            application.id,
            name="renamed",
            description="",
            organization_ids=[30],
            actor="tester",
        )

    application.refresh_from_db()
    discovered.service.refresh_from_db()
    discovered.instance.refresh_from_db()
    assert application.name == original_name
    assert set(application.organization_links.values_list("organization", flat=True)) == {10}
    assert set(discovered.service.organization_links.values_list("organization", flat=True)) == {10}
    assert set(discovered.instance.organization_links.values_list("organization", flat=True)) == {10}


def test_latest_observation_updates_metadata_without_regressing_on_stale_data():
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    now = timezone.now()
    first = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "testing", seen_at=now))

    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "production", version="2.0", seen_at=now + timedelta(minutes=1)))
    catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "stale", version="1.0", seen_at=now - timedelta(minutes=1)))

    first.instance.refresh_from_db()
    assert first.instance.environment == "production"
    assert first.instance.version == "2.0"
    assert first.instance.last_seen_at == now + timedelta(minutes=1)
    assert ApmServiceOrganization.objects.filter(service=first.service).count() == 1
