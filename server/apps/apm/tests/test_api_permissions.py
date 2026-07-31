import pytest
from rest_framework.test import APIClient

from apps.apm.models import ApmIngestSource
from apps.apm.services import DjangoIngestSourceService, DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery


pytestmark = pytest.mark.django_db


def test_create_shows_plaintext_once_and_never_serializes_digest(apm_api_client):
    response = apm_api_client.post(
        "/api/v1/apm/ingest-sources/",
        {
            "name": "checkout",
            "ingest_type": "otlp_http",
            "organization_ids": [10],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["credential"].startswith("bkapm_")
    assert "credential_digest" not in response.data
    source = ApmIngestSource.objects.get(id=response.data["id"])
    assert source.credential_digest != response.data["credential"]

    listed = apm_api_client.get("/api/v1/apm/ingest-sources/")
    assert listed.status_code == 200
    assert "credential" not in listed.data[0]
    assert "credential_digest" not in listed.data[0]


def test_view_permission_is_required(apm_user_without_permissions):
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/services/")

    assert response.status_code == 403


def test_operate_permission_is_required_for_ingest_changes(apm_user):
    apm_user.permission["apm"] = {"integration_add-View"}
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"

    response = client.post(
        "/api/v1/apm/ingest-sources/",
        {
            "name": "checkout",
            "ingest_type": "otlp_http",
            "organization_ids": [10],
        },
        format="json",
    )

    assert response.status_code == 403
    assert ApmIngestSource.objects.count() == 0


def test_service_and_instance_lists_use_their_independent_organization_scopes(apm_api_client):
    ingest_service = DjangoIngestSourceService()
    catalog = DjangoTelemetryCatalogService()
    source_10 = ingest_service.create(
        name="source-10",
        ingest_type="otlp_http",
        organization_ids=[10],
        actor="tester",
    ).source
    source_20 = ingest_service.create(
        name="source-20",
        ingest_type="otlp_http",
        organization_ids=[20],
        actor="tester",
    ).source
    visible = catalog.discover(
        CatalogDiscovery(source_10.id, "shop", "checkout", "pod-a", "prod")
    )
    hidden = catalog.discover(
        CatalogDiscovery(source_20.id, "billing", "invoice", "pod-b", "prod")
    )

    services = apm_api_client.get("/api/v1/apm/services/")
    instances = apm_api_client.get("/api/v1/apm/instances/")
    hidden_service = apm_api_client.get(f"/api/v1/apm/services/{hidden.service.id}/")
    hidden_instance = apm_api_client.get(f"/api/v1/apm/instances/{hidden.instance.id}/")

    assert services.status_code == 200
    assert [item["id"] for item in services.data] == [str(visible.service.id)]
    assert instances.status_code == 200
    assert [item["id"] for item in instances.data] == [str(visible.instance.id)]
    assert hidden_service.status_code == 404
    assert hidden_instance.status_code == 404
