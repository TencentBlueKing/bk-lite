import os
import shlex
import subprocess
import uuid
from unittest.mock import Mock
from urllib.parse import unquote

import pytest
from rest_framework.test import APIClient

from apps.apm.models import ApmApplication
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _configuration_script(code: str) -> str:
    section = code.split("# 2. 配置上报", maxsplit=1)[1].split("# 3. 启动应用", maxsplit=1)[0]
    return section.split("\n", maxsplit=1)[1]


def _integration_region(monkeypatch):
    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "华东一区"}]
    region.get_cloud_region_proxy_address.return_value = "apm-east.example.com"
    region.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "http://10.10.10.1:8011"}
    monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
    return region


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


def test_application_catalog_does_not_expose_a_builtin_uncategorized_application(apm_api_client):
    listed = apm_api_client.get("/api/v1/apm/applications/")

    assert listed.status_code == 200
    assert listed.data == []
    assert not ApmApplication.objects.filter(is_builtin=True).exists()


def test_application_update_ignores_immutable_application_id_from_stale_payload(apm_api_client):
    created = apm_api_client.post(
        "/api/v1/apm/applications/",
        {
            "application_id": "shop",
            "name": "电商主站",
            "organization_ids": [10],
        },
        format="json",
    )
    assert created.status_code == 201

    with_current_id = apm_api_client.put(
        f"/api/v1/apm/applications/{created.data['id']}/",
        {
            "application_id": "shop",
            "name": "电商主站-2",
            "description": "",
            "organization_ids": [10],
        },
        format="json",
    )
    with_blank_id = apm_api_client.put(
        f"/api/v1/apm/applications/{created.data['id']}/",
        {
            "application_id": "",
            "name": "电商主站-3",
            "description": "",
            "organization_ids": [10],
        },
        format="json",
    )

    assert with_current_id.status_code == 200
    assert with_current_id.data["application_id"] == "shop"
    assert with_current_id.data["name"] == "电商主站-2"
    assert with_blank_id.status_code == 200
    assert with_blank_id.data["application_id"] == "shop"
    assert with_blank_id.data["name"] == "电商主站-3"


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
    region.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "http://10.10.10.1:8011"}

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
    assert "http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-python-wheels.tar.gz" in response.data["code"]
    assert "pypi.org" not in response.data["code"]
    region.get_cloud_region_proxy_address.assert_called_once_with(7)
    region.get_cloud_region_public_config.assert_called_once_with(7)
    assert ApmApplication.objects.filter(is_builtin=False).count() == 1


def test_integration_config_host_identity_is_generated_per_process_and_can_be_safely_overridden(
    apm_api_client,
    monkeypatch,
):
    create_application("shop", (10,))
    _integration_region(monkeypatch)
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
    configuration = _configuration_script(response.data["code"])
    generated = []
    for _ in range(2):
        result = subprocess.run(
            ["/bin/sh", "-c", f'{configuration}\nprintf %s "$OTEL_SERVICE_INSTANCE_ID"'],
            env={key: value for key, value in os.environ.items() if key != "APM_INSTANCE_ID"},
            text=True,
            capture_output=True,
            check=True,
        )
        generated.append(result.stdout)
        assert uuid.UUID(result.stdout).version == 4
    assert generated[0] != generated[1]

    overridden = subprocess.run(
        ["/bin/sh", "-c", f'{configuration}\nprintf %s "$OTEL_SERVICE_INSTANCE_ID"'],
        env={**os.environ, "APM_INSTANCE_ID": "host-replica-a"},
        text=True,
        capture_output=True,
        check=True,
    )
    assert overridden.stdout == "host-replica-a"
    assert "每个副本必须唯一" in response.data["code"]


def test_integration_config_host_identity_generation_and_invalid_override_fail_closed(
    apm_api_client,
    monkeypatch,
    tmp_path,
):
    create_application("shop", (10,))
    _integration_region(monkeypatch)
    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": "python",
            "runtime": "host",
            "service_name": "checkout",
            "environment": "production",
        },
        format="json",
    )

    configuration = _configuration_script(response.data["code"])
    unavailable = subprocess.run(
        ["/bin/sh", "-c", configuration],
        env={"PATH": str(tmp_path)},
        text=True,
        capture_output=True,
    )
    invalid_override = subprocess.run(
        ["/bin/sh", "-c", configuration],
        env={**os.environ, "APM_INSTANCE_ID": "shared,replica"},
        text=True,
        capture_output=True,
    )

    assert unavailable.returncode != 0
    assert invalid_override.returncode != 0
    assert "service.instance.id" in unavailable.stderr
    assert "service.instance.id" in invalid_override.stderr


@pytest.mark.parametrize("runtime", ["host", "docker"])
def test_integration_config_encodes_special_resource_values_without_shell_or_attribute_injection(
    apm_api_client,
    monkeypatch,
    runtime,
):
    create_application("shop", (10,))
    _integration_region(monkeypatch)
    malicious = "checkout%'\n,service.instance.id=forged $(printf injected) `printf injected` 界"
    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": "python",
            "runtime": runtime,
            "service_name": malicious,
            "service_version": malicious,
            "environment": malicious,
        },
        format="json",
    )

    assert response.status_code == 200
    assert subprocess.run(["/bin/sh", "-n"], input=response.data["code"], text=True).returncode == 0
    resource_dto = response.data["environment"]["OTEL_RESOURCE_ATTRIBUTES"]
    assert "%25" in resource_dto
    assert "%2Cservice.instance.id%3Dforged" in resource_dto
    assert "%0A" in resource_dto
    assert "%E7%95%8C" in resource_dto

    if runtime == "host":
        script = _configuration_script(response.data["code"])
        script += '\nprintf %s "$OTEL_RESOURCE_ATTRIBUTES"'
        environment = {**os.environ, "APM_INSTANCE_ID": "host-instance"}
    else:
        tokens = shlex.split(response.data["code"], comments=True)
        command_index = next(index for index in range(len(tokens) - 2) if tokens[index : index + 2] == ["sh", "-c"])
        script_token = next(token for token in tokens[command_index + 2 :] if token.strip())
        script = script_token.split("; exec ", maxsplit=1)[0]
        script += '\nprintf %s "$OTEL_RESOURCE_ATTRIBUTES"'
        environment = {
            **{key: value for key, value in os.environ.items() if key != "APM_INSTANCE_ID"},
            "HOSTNAME": "container-instance",
        }
    rendered = subprocess.run(
        ["/bin/sh", "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    pairs = dict(item.split("=", maxsplit=1) for item in rendered.stdout.split(","))
    decoded = {key: unquote(value) for key, value in pairs.items()}
    assert set(decoded) == {
        "service.namespace",
        "service.name",
        "service.version",
        "deployment.environment",
        "service.instance.id",
    }
    assert decoded["service.name"] == malicious
    assert decoded["service.version"] == malicious
    assert decoded["deployment.environment"] == malicious
    assert decoded["service.instance.id"] == ("host-instance" if runtime == "host" else "container-instance")


def test_integration_config_falls_back_to_trusted_node_server_url_without_node_organization(apm_api_client):
    create_application("shop", (10,))
    region = Mock()
    region.cloud_region_list.return_value = [{"id": 7, "name": "直连区域"}]
    region.get_cloud_region_proxy_address.return_value = ""
    region.get_cloud_region_public_config.return_value = {
        "NODE_SERVER_URL": "http://10.10.10.1:8011",
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("apps.apm.views.control_plane.NodeMgmt", lambda: region)
        response = apm_api_client.post(
            "/api/v1/apm/integration-config/",
            {
                "application_id": "shop",
                "cloud_region_id": 7,
                "language": "nodejs",
                "runtime": "host",
                "service_name": "checkout",
                "service_version": "1.4.0",
                "environment": "production",
            },
            format="json",
        )

    assert response.status_code == 200
    assert response.data["http_endpoint"] == "http://10.10.10.1:4318/v1/traces"
    assert response.data["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://10.10.10.1:4318"
    region.get_cloud_region_proxy_address.assert_called_once_with(7)
    region.get_cloud_region_public_config.assert_called_once_with(7)


def test_integration_config_java_snippet_uses_the_system_probe_download_address(apm_api_client, monkeypatch):
    create_application("shop", (10,))
    region = _integration_region(monkeypatch)
    region.get_cloud_region_public_config.return_value = {"NODE_SERVER_URL": "http://10.10.10.1:8011"}

    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": "java",
            "runtime": "host",
            "service_name": "checkout",
            "service_version": "1.4.0",
            "environment": "production",
        },
        format="json",
    )

    assert response.status_code == 200
    assert "http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar" in response.data["code"]
    assert "github.com" not in response.data["code"]
    region.get_cloud_region_public_config.assert_called_once_with(7)


@pytest.mark.parametrize(
    ("language", "artifact_name", "forbidden"),
    [
        ("python", "opentelemetry-python-wheels.tar.gz", "pypi.org"),
        ("nodejs", "opentelemetry-js-auto.tgz", "npmjs"),
        ("go", "opentelemetry-go-sdk.zip", "go get "),
    ],
)
def test_integration_config_snippets_use_system_probe_download_addresses(
    apm_api_client,
    monkeypatch,
    language,
    artifact_name,
    forbidden,
):
    create_application("shop", (10,))
    _integration_region(monkeypatch)

    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": language,
            "runtime": "host",
            "service_name": "checkout",
            "service_version": "1.4.0",
            "environment": "production",
        },
        format="json",
    )

    assert response.status_code == 200
    assert f"http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/{artifact_name}" in response.data["code"]
    assert forbidden not in response.data["code"]


def test_integration_config_java_snippet_reports_missing_probe_download_address(apm_api_client, monkeypatch):
    create_application("shop", (10,))
    region = _integration_region(monkeypatch)
    region.get_cloud_region_public_config.return_value = {}

    response = apm_api_client.post(
        "/api/v1/apm/integration-config/",
        {
            "application_id": "shop",
            "cloud_region_id": 7,
            "language": "java",
            "runtime": "host",
            "service_name": "checkout",
            "environment": "production",
        },
        format="json",
    )

    assert response.status_code == 404
    assert response.data["code"] == "probe_download_unavailable"


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
    assert response.data == []


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


def test_service_archive_and_catalog_organization_actions_remain_real_but_instance_archive_is_removed(apm_api_client):
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
    assert archived_service.data["status"] == "archived"
    assert archived_instance.status_code == 404
    assert apm_api_client.post(f"/api/v1/apm/services/{discovered.service.id}/restore/").status_code == 200
    assert apm_api_client.post(f"/api/v1/apm/instances/{discovered.instance.id}/restore/").status_code == 404
