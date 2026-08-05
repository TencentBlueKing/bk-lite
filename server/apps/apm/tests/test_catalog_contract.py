from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.models import ApmApplication, ApmService, ApmServiceInstance, ApmServiceOrganization
from apps.apm.services import DjangoApmApplicationService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application


pytestmark = pytest.mark.django_db


def test_service_and_instance_are_discovered_under_a_known_application():
    application = create_application("shop", (10, 20))

    result = DjangoTelemetryCatalogService().discover(
        CatalogDiscovery("shop", " checkout ", "pod-a", "production", version="1.2.3")
    )

    assert result.service.application == application
    assert result.service.normalized_namespace == "shop"
    assert result.instance.service == result.service
    assert result.instance.version == "1.2.3"
    assert set(result.service.organization_links.values_list("organization", flat=True)) == {10, 20}
    assert set(result.instance.organization_links.values_list("organization", flat=True)) == {10, 20}


def test_unknown_or_disabled_application_cannot_create_catalog_rows():
    disabled = create_application("disabled", (10,))
    disabled.is_enabled = False
    disabled.save(update_fields=("is_enabled", "updated_at"))
    catalog = DjangoTelemetryCatalogService()

    with pytest.raises(ApmApplication.DoesNotExist):
        catalog.discover(CatalogDiscovery("unknown", "checkout", "pod-a", "prod"))
    with pytest.raises(ApmApplication.DoesNotExist):
        catalog.discover(CatalogDiscovery("disabled", "checkout", "pod-a", "prod"))

    assert ApmService.objects.count() == 0
    assert ApmServiceInstance.objects.count() == 0


def test_missing_instance_identity_discovers_service_without_fake_instance():
    create_application("shop", (10,))

    result = DjangoTelemetryCatalogService().discover(
        CatalogDiscovery("shop", "checkout", None, "prod")
    )

    assert result.missing_instance_identity is True
    assert result.service is not None
    assert result.instance is None
    assert ApmServiceInstance.objects.count() == 0


def test_application_organization_changes_follow_only_inherited_instances():
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
        is_enabled=True,
    )
    custom.refresh_from_db()

    assert set(inherited.organization_links.values_list("organization", flat=True)) == {30}
    assert set(custom.organization_links.values_list("organization", flat=True)) == {20}
    assert custom.permission_mode == ApmServiceInstance.PermissionMode.CUSTOM


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
