from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.models import ApmApplicationOrganization, ApmServiceInstanceOrganization, ApmServiceOrganization
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application
from apps.base.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _discover(namespace, service_name, instance_id, *, seen_at):
    return DjangoTelemetryCatalogService().discover(
        CatalogDiscovery(namespace, service_name, instance_id, "prod", seen_at=seen_at)
    )


def _wipe_orgs(discovery, application):
    ApmApplicationOrganization.objects.filter(application=application).delete()
    ApmServiceOrganization.objects.filter(service=discovery.service).delete()
    ApmServiceInstanceOrganization.objects.filter(instance=discovery.instance).delete()


@pytest.fixture
def apm_superuser_client():
    user = UserFactory(
        username="apm-super",
        domain="domain.com",
        group_list=[{"id": 10, "name": "Team 10"}],
        roles=[],
        is_superuser=True,
    )
    user.permission = {
        "apm": {
            "applications-View",
            "applications-Operate",
            "integration_instances-View",
            "integration_instances-Operate",
            "services-View",
            "services-Operate",
            "traces-View",
        }
    }
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["current_team"] = "10"
    return client


def test_superuser_default_lists_hide_unassigned_catalog(apm_superuser_client):
    now = timezone.now()
    visible_app = create_application("shop", (10,))
    ghost_app = create_application("ghost", (10,))
    visible = _discover("shop", "checkout-api", "pod-visible", seen_at=now)
    ghost = _discover("ghost", "ghost-api", "pod-ghost", seen_at=now - timedelta(minutes=1))
    _wipe_orgs(ghost, ghost_app)

    services = apm_superuser_client.get("/api/v1/apm/services/")
    instances = apm_superuser_client.get("/api/v1/apm/instances/")
    applications = apm_superuser_client.get("/api/v1/apm/applications/")

    assert services.status_code == instances.status_code == applications.status_code == 200
    assert {item["id"] for item in services.data} == {str(visible.service.id)}
    instance_rows = instances.data if isinstance(instances.data, list) else instances.data["items"]
    assert {item["id"] for item in instance_rows} == {str(visible.instance.id)}
    assert {item["application_id"] for item in applications.data} == {visible_app.application_id}


def test_superuser_unassigned_lists_show_only_zero_org_catalog(apm_superuser_client):
    now = timezone.now()
    create_application("shop", (10,))
    ghost_app = create_application("ghost", (10,))
    _discover("shop", "checkout-api", "pod-visible", seen_at=now)
    ghost = _discover("ghost", "ghost-api", "pod-ghost", seen_at=now - timedelta(minutes=1))
    _wipe_orgs(ghost, ghost_app)

    services = apm_superuser_client.get("/api/v1/apm/services/", {"unassigned": "true"})
    instances = apm_superuser_client.get("/api/v1/apm/instances/", {"unassigned": "true"})
    applications = apm_superuser_client.get("/api/v1/apm/applications/", {"unassigned": "true"})

    assert {item["id"] for item in services.data} == {str(ghost.service.id)}
    instance_rows = instances.data if isinstance(instances.data, list) else instances.data["items"]
    assert {item["id"] for item in instance_rows} == {str(ghost.instance.id)}
    assert {item["application_id"] for item in applications.data} == {ghost_app.application_id}


def test_non_superuser_unassigned_list_is_forbidden(apm_api_client):
    response = apm_api_client.get("/api/v1/apm/services/", {"unassigned": "true"})

    assert response.status_code == 403


def test_superuser_can_retrieve_and_reassign_unassigned_service(apm_superuser_client):
    now = timezone.now()
    ghost_app = create_application("ghost", (10,))
    ghost = _discover("ghost", "ghost-api", "pod-ghost", seen_at=now)
    _wipe_orgs(ghost, ghost_app)

    detail = apm_superuser_client.get(f"/api/v1/apm/services/{ghost.service.id}/")
    assigned = apm_superuser_client.put(
        f"/api/v1/apm/services/{ghost.service.id}/organizations/",
        {"organization_ids": [10]},
        format="json",
    )

    assert detail.status_code == 200
    assert assigned.status_code == 200
    assert assigned.data["organization_ids"] == [10]
    listed = apm_superuser_client.get("/api/v1/apm/services/")
    assert str(ghost.service.id) in {item["id"] for item in listed.data}
    unassigned = apm_superuser_client.get("/api/v1/apm/services/", {"unassigned": "true"})
    assert str(ghost.service.id) not in {item["id"] for item in unassigned.data}
