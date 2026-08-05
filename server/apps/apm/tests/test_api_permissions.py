import pytest
from rest_framework.test import APIClient

from apps.apm.models import ApmApplication
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application


pytestmark = pytest.mark.django_db


def test_application_crud_persists_business_boundary_without_a_token(apm_api_client):
    created = apm_api_client.post(
        "/api/v1/apm/applications/",
        {
            "application_id": "shop",
            "name": "电商主站",
            "description": "交易入口",
            "organization_ids": [10, 20],
        },
        format="json",
    )

    assert created.status_code == 201
    assert created.data["application_id"] == "shop"
    assert created.data["organization_ids"] == [10, 20]
    assert "credential" not in created.data
    assert ApmApplication.objects.count() == 1

    updated = apm_api_client.put(
        f"/api/v1/apm/applications/{created.data['id']}/",
        {
            "name": "电商应用",
            "description": "",
            "organization_ids": [10],
            "is_enabled": False,
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["application_id"] == "shop"
    assert updated.data["name"] == "电商应用"
    assert updated.data["is_enabled"] is False


def test_application_id_validation_and_uniqueness_are_explicit(apm_api_client):
    invalid = apm_api_client.post(
        "/api/v1/apm/applications/",
        {"application_id": "bad id", "name": "bad", "organization_ids": [10]},
        format="json",
    )
    first = apm_api_client.post(
        "/api/v1/apm/applications/",
        {"application_id": "shop", "name": "shop", "organization_ids": [10]},
        format="json",
    )
    duplicate = apm_api_client.post(
        "/api/v1/apm/applications/",
        {"application_id": "shop", "name": "other", "organization_ids": [10]},
        format="json",
    )

    assert invalid.status_code == 400
    assert first.status_code == 201
    assert duplicate.status_code == 400


def test_integration_config_is_stateless_and_maps_standard_resource_attributes(apm_api_client):
    create_application("shop", (10,))

    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "language": "python",
            "runtime": "host",
            "endpoint": "https://apm.example.com",
            "service_name": "checkout",
            "service_version": "1.4.0",
            "environment": "production",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["application_id"] == "shop"
    resource = response.data["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.namespace=shop" in resource
    assert "service.name=checkout" in resource
    assert "service.version=1.4.0" in resource
    assert "Authorization" not in response.data["code"]
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in response.data["environment"]
    assert ApmApplication.objects.count() == 1


def test_integration_config_rejects_unknown_or_out_of_scope_application(apm_api_client):
    create_application("hidden", (20,))

    unknown = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {"application_id": "unknown", "language": "java", "runtime": "host", "endpoint": "https://apm.example.com", "service_name": "api", "environment": "prod"},
        format="json",
    )
    hidden = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {"application_id": "hidden", "language": "java", "runtime": "host", "endpoint": "https://apm.example.com", "service_name": "api", "environment": "prod"},
        format="json",
    )

    assert unknown.status_code == hidden.status_code == 404


def test_permissions_separate_application_management_from_config_generation(apm_user):
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"
    apm_user.permission["apm"] = {"integration_add-View"}

    denied = client.post(
        "/api/v1/apm/applications/",
        {"application_id": "shop", "name": "shop", "organization_ids": [10]},
        format="json",
    )
    assert denied.status_code == 403
    assert ApmApplication.objects.count() == 0


def test_service_and_instance_lists_keep_independent_organization_scopes(apm_api_client):
    create_application("shop", (10,))
    create_application("billing", (20,))
    catalog = DjangoTelemetryCatalogService()
    visible = catalog.discover(CatalogDiscovery("shop", "checkout", "pod-a", "prod"))
    hidden = catalog.discover(CatalogDiscovery("billing", "invoice", "pod-b", "prod"))

    services = apm_api_client.get("/api/v1/apm/services/")
    instances = apm_api_client.get("/api/v1/apm/instances/")

    assert [item["id"] for item in services.data] == [str(visible.service.id)]
    assert [item["id"] for item in instances.data] == [str(visible.instance.id)]
    assert apm_api_client.get(f"/api/v1/apm/services/{hidden.service.id}/").status_code == 404
    assert apm_api_client.get(f"/api/v1/apm/instances/{hidden.instance.id}/").status_code == 404


def test_service_and_instance_organization_archive_restore_actions_remain_real(apm_api_client):
    create_application("shop", (10,))
    discovered = DjangoTelemetryCatalogService().discover(CatalogDiscovery("shop", "checkout", "pod-a", "prod"))

    service_orgs = apm_api_client.put(f"/api/v1/apm/services/{discovered.service.id}/organizations/", {"organization_ids": [10, 20]}, format="json")
    instance_orgs = apm_api_client.put(f"/api/v1/apm/instances/{discovered.instance.id}/organizations/", {"organization_ids": [10, 30]}, format="json")
    archived_service = apm_api_client.post(f"/api/v1/apm/services/{discovered.service.id}/archive/", {"reason": "manual"}, format="json")
    archived_instance = apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/archive/", {"reason": "manual"}, format="json")

    assert service_orgs.data["organization_ids"] == [10, 20]
    assert instance_orgs.data["organization_ids"] == [10, 30]
    assert archived_service.data["status"] == archived_instance.data["status"] == "archived"
    assert apm_api_client.post(f"/api/v1/apm/services/{discovered.service.id}/restore/").status_code == 200
    assert apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/restore/").status_code == 200
