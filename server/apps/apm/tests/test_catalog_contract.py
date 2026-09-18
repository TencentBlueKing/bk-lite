from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.models import (
    ApmApplication,
    ApmService,
    ApmServiceInstance,
    ApmServiceInstanceOrganization,
    ApmServiceOrganization,
)
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


def test_empty_namespace_cannot_create_an_uncategorized_catalog_row():
    with pytest.raises(ApmApplication.DoesNotExist):
        DjangoTelemetryCatalogService().discover(CatalogDiscovery("", "kernel-worker", "node-a", "prod"))

    assert ApmService.objects.count() == 0


def test_missing_instance_identity_discovers_service_without_fake_instance():
    create_application("shop", (10,))

    result = DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", "checkout", None, "prod"))

    assert result.missing_instance_identity is True
    assert result.service is not None
    assert result.instance is None
    assert ApmServiceInstance.objects.count() == 0


def test_latest_sdk_language_is_stored_on_the_service():
    create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    first = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "prod", language="python"))

    catalog.discover(
        CatalogDiscovery(
            "shop",
            "checkout",
            "pod-a",
            "prod",
            language="java",
            seen_at=first.service.last_seen_at + timedelta(minutes=1),
        )
    )

    first.service.refresh_from_db()
    assert first.service.language == "java"


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


def test_adding_one_organization_only_writes_delta_authorization_rows(mocker):
    application = create_application("shop", (10,))
    catalog = DjangoTelemetryCatalogService()
    inherited_instances = [
        catalog.discover(CatalogDiscovery("shop", "checkout", f"pod-{index}", "prod")).instance
        for index in range(20)
    ]
    custom = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-custom", "prod")).instance
    catalog.set_instance_organizations(custom.id, [20], actor="tester")
    kept_service_org_ids = list(
        ApmServiceOrganization.objects.filter(service=inherited_instances[0].service, organization=10).values_list("id", flat=True)
    )
    kept_instance_org_ids = list(
        ApmServiceInstanceOrganization.objects.filter(
            instance_id__in=[instance.id for instance in inherited_instances],
            organization=10,
        ).values_list("id", flat=True)
    )
    original_service_bulk_create = ApmServiceOrganization.objects.bulk_create
    original_instance_bulk_create = ApmServiceInstanceOrganization.objects.bulk_create
    created_service_rows: list[ApmServiceOrganization] = []
    created_instance_rows: list[ApmServiceInstanceOrganization] = []

    def counting_service_bulk_create(objs, **kwargs):
        rows = list(objs)
        created_service_rows.extend(rows)
        return original_service_bulk_create(rows, **kwargs)

    def counting_instance_bulk_create(objs, **kwargs):
        rows = list(objs)
        created_instance_rows.extend(rows)
        return original_instance_bulk_create(rows, **kwargs)

    mocker.patch(
        "apps.apm.services.applications.ApmServiceOrganization.objects.bulk_create",
        side_effect=counting_service_bulk_create,
    )
    mocker.patch(
        "apps.apm.services.applications.ApmServiceInstanceOrganization.objects.bulk_create",
        side_effect=counting_instance_bulk_create,
    )

    DjangoApmApplicationService().update(
        application.id,
        name=application.name,
        description="",
        organization_ids=[10, 30],
        actor="tester",
    )
    custom.refresh_from_db()
    inherited_instances[0].service.refresh_from_db()

    assert len(created_service_rows) == 1
    assert len(created_instance_rows) == 20
    assert {row.organization for row in created_service_rows} == {30}
    assert {row.organization for row in created_instance_rows} == {30}
    assert set(inherited_instances[0].service.organization_links.values_list("organization", flat=True)) == {10, 30}
    assert set(
        ApmServiceInstanceOrganization.objects.filter(
            instance_id__in=[instance.id for instance in inherited_instances]
        ).values_list("organization", flat=True)
    ) == {10, 30}
    assert list(
        ApmServiceOrganization.objects.filter(service=inherited_instances[0].service, organization=10).values_list("id", flat=True)
    ) == kept_service_org_ids
    assert list(
        ApmServiceInstanceOrganization.objects.filter(
            instance_id__in=[instance.id for instance in inherited_instances],
            organization=10,
        ).values_list("id", flat=True)
    ) == kept_instance_org_ids
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
