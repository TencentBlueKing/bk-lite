from unittest.mock import Mock

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
    assert created.data["is_builtin"] is False
    assert created.data["organization_ids"] == [10, 20]
    assert "credential" not in created.data
    assert ApmApplication.objects.filter(is_builtin=False).count() == 1

    updated = apm_api_client.put(
        f"/api/v1/apm/applications/{created.data['id']}/",
        {
            "name": "电商应用",
            "description": "",
            "organization_ids": [10],
            "is_builtin": True,
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["application_id"] == "shop"
    assert updated.data["name"] == "电商应用"
    assert updated.data["is_builtin"] is False


def test_builtin_application_is_visible_but_cannot_be_modified(apm_api_client):
    application = ApmApplication.objects.get(application_id="", is_builtin=True)

    listed = apm_api_client.get("/api/v1/apm/applications/")
    updated = apm_api_client.put(
        f"/api/v1/apm/applications/{application.id}/",
        {
            "name": "被篡改的名称",
            "description": "",
            "organization_ids": [10],
        },
        format="json",
    )
    deleted = apm_api_client.delete(f"/api/v1/apm/applications/{application.id}/")

    assert listed.status_code == 200
    assert listed.data[0]["is_builtin"] is True
    assert updated.status_code == 409
    assert updated.data["detail"] == "内置应用不可修改。"
    assert deleted.status_code == 405
    application.refresh_from_db()
    assert application.name == "未归类应用"


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

    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = "apm-east.example.com"

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        response = apm_api_client.post(
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

    assert response.status_code == 200
    assert response.data["application_id"] == "shop"
    resource = response.data["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
    assert "service.namespace=shop" in resource
    assert "service.name=checkout" in resource
    assert "service.version=1.4.0" in resource
    assert "Authorization" not in response.data["code"]
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in response.data["environment"]
    assert response.data["cloud_region"] == {"id": 7, "name": "华东一区"}
    assert response.data["http_endpoint"] == "http://apm-east.example.com:4318/v1/traces"
    assert "grpc_endpoint" not in response.data
    assert response.data["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://apm-east.example.com:4318"
    region.get_cloud_region_proxy_address.assert_called_once_with(7, [10])
    region.get_cloud_region_envconfig.assert_not_called()
    assert ApmApplication.objects.filter(is_builtin=False).count() == 1


def test_integration_config_rejects_unknown_or_out_of_scope_application(apm_api_client):
    create_application("hidden", (20,))

    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = "apm-east.example.com"

    payload = {
        "cloud_region_id": 7,
        "language": "java",
        "runtime": "host",
        "service_name": "api",
        "environment": "prod",
    }
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        unknown = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {"application_id": "unknown", **payload},
            format="json",
        )
        hidden = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {"application_id": "hidden", **payload},
            format="json",
        )

    assert unknown.status_code == hidden.status_code == 404


def test_integration_config_lists_regions_with_apm_permission(apm_api_client):
    region = Mock()
    region.cloud_region_list.return_value = [
        {"id": 7, "name": "华东一区"},
        {"id": 9, "name": "海外一区"},
    ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        response = apm_api_client.get("/api/v1/apm/integration-config/regions/")

    assert response.status_code == 200
    assert response.data == [{"id": 7, "name": "华东一区"}, {"id": 9, "name": "海外一区"}]


def test_integration_config_regions_require_apm_permission(apm_user_without_permissions):
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/integration-config/regions/")

    assert response.status_code == 403


def test_integration_config_reports_region_directory_unavailable(apm_api_client):
    region = Mock()
    region.cloud_region_list.side_effect = TimeoutError("rpc timeout")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        response = apm_api_client.get("/api/v1/apm/integration-config/regions/")

    assert response.status_code == 503
    assert response.data["code"] == "cloud_region_unavailable"
    assert "rpc timeout" not in str(response.data)


def test_integration_config_rejects_client_endpoint_and_invalid_region_proxy_address(apm_api_client):
    create_application("shop", (10,))
    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = "https://attacker.example.com/path"
    payload = {
        "application_id": "shop",
        "cloud_region_id": 7,
        "language": "python",
        "runtime": "host",
        "service_name": "api",
        "environment": "prod",
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        injected = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {**payload, "endpoint": "http://attacker.example.com:4318"},
            format="json",
        )
        invalid_config = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            payload,
            format="json",
        )

    assert injected.status_code == 400
    assert "服务器" in str(injected.data)
    assert invalid_config.status_code == 400
    assert invalid_config.data["code"] == "invalid_cloud_region_proxy_address"


def test_integration_config_distinguishes_unknown_region_and_missing_proxy_address(apm_api_client):
    create_application("shop", (10,))
    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = ""
    payload = {
        "application_id": "shop",
        "language": "python",
        "runtime": "host",
        "service_name": "api",
        "environment": "prod",
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        unknown = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {**payload, "cloud_region_id": 404},
            format="json",
        )
        missing = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {**payload, "cloud_region_id": 7},
            format="json",
        )

    assert unknown.status_code == 404
    assert missing.status_code == 404
    assert missing.data["code"] == "cloud_region_receiver_unavailable"


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
    assert ApmApplication.objects.filter(is_builtin=False).count() == 0


def test_service_catalog_permission_can_read_application_boundaries(apm_user):
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"
    apm_user.permission["apm"] = {"services-View"}

    response = client.get("/api/v1/apm/applications/")

    assert response.status_code == 200
    assert [(item["name"], item["is_builtin"]) for item in response.data] == [("未归类应用", True)]


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
    instance_orgs = apm_api_client.put(
        f"/api/v1/apm/instances/{discovered.instance.id}/organizations/", {"organization_ids": [10, 30]}, format="json"
    )
    archived_service = apm_api_client.post(f"/api/v1/apm/services/{discovered.service.id}/archive/", {"reason": "manual"}, format="json")
    archived_instance = apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/archive/", {"reason": "manual"}, format="json")

    assert service_orgs.data["organization_ids"] == [10, 20]
    assert instance_orgs.data["organization_ids"] == [10, 30]
    assert archived_service.data["status"] == archived_instance.data["status"] == "archived"
    assert apm_api_client.post(f"/api/v1/apm/services/{discovered.service.id}/restore/").status_code == 200
    assert apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/restore/").status_code == 200
