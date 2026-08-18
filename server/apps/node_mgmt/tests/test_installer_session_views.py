import json
import re

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory

from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, PackageVersion, SidecarEnv
from apps.node_mgmt.services.install_token import InstallTokenService
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.views.sidecar import OpenSidecarViewSet


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "installer-session-view-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.mark.parametrize(
    ("url", "exposes_remaining_usage"),
    [
        pytest.param("/api/v1/node_mgmt/open_api/installer/session", True, id="session"),
        pytest.param("/api/v1/node_mgmt/open_api/installer/linux_bootstrap", False, id="linux-bootstrap"),
    ],
)
def test_strict_credentials_failure_does_not_consume_install_token(
    monkeypatch,
    capfd,
    url,
    exposes_remaining_usage,
):
    cloud_region = CloudRegion.objects.create(
        name="strict-installer-session",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    env_values = {
        NodeConstants.SERVER_URL_KEY: "https://server.example",
        NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
        "NATS_PROTOCOL": "tls",
        "NATS_ADMIN_USERNAME": "admin-user-not-for-error-response",
        NodeConstants.NATS_ADMIN_PASSWORD_KEY: "admin-password-not-for-error-response",
        NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY: NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
    }
    for key, value in env_values.items():
        SidecarEnv.objects.create(key=key, value=value, type="text", cloud_region=cloud_region)

    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    token = InstallTokenService.generate_install_token(
        node_id="node-strict",
        ip="10.0.0.9",
        user="root",
        os=NodeConstants.LINUX_OS,
        package_id=str(package.id),
        cloud_region_id=str(cloud_region.id),
        organizations=[],
        node_name="node-strict",
        cpu_architecture=NodeConstants.X86_64_ARCH,
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda _: "linux/Controller/1.0.0/controller.tar.gz",
    )
    client = APIClient()

    failed_response = client.get(url, {"token": token})
    captured_logs = capfd.readouterr()

    assert failed_response.status_code == 400
    failed_body = json.dumps(failed_response.json())
    assert "strict mode requires dedicated" in failed_body
    assert env_values["NATS_ADMIN_USERNAME"] not in failed_body
    assert env_values[NodeConstants.NATS_ADMIN_PASSWORD_KEY] not in failed_body
    assert token not in captured_logs.out
    assert token not in captured_logs.err
    usage_key = (
        f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}:"
        f"{InstallTokenService.USAGE_COUNT_CACHE_SUFFIX}"
    )
    assert cache.get(usage_key) in (None, 0)

    SidecarEnv.objects.filter(
        cloud_region=cloud_region,
        key=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY,
    ).update(value=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_LEGACY)

    recovered_response = client.get(url, {"token": token})

    assert recovered_response.status_code == 200
    if exposes_remaining_usage:
        assert recovered_response["X-Token-Remaining-Usage"] == str(
            InstallerConstants.INSTALL_TOKEN_MAX_USAGE - 1
        )
    assert cache.get(usage_key) == 1


@pytest.mark.parametrize("install_mode", ["manual", "auto"])
def test_linux_command_issuance_does_not_consume_install_token(monkeypatch, install_mode):
    cloud_region = CloudRegion.objects.create(
        name=f"linux-command-{install_mode}",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    env_values = {
        NodeConstants.SERVER_URL_KEY: "https://server.example",
        NodeConstants.NATS_SERVERS_KEY: "tls://nats.example:4222",
        "NATS_PROTOCOL": "tls",
        NodeConstants.NATS_INSTALLER_USERNAME_KEY: "installer-user",
        NodeConstants.NATS_INSTALLER_PASSWORD_KEY: "installer-password",
        NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY: NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
    }
    for key, value in env_values.items():
        SidecarEnv.objects.create(key=key, value=value, type="text", cloud_region=cloud_region)

    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="controller.tar.gz",
        created_by="tester",
        updated_by="tester",
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda _: "linux/Controller/1.0.0/controller.tar.gz",
    )

    command = InstallerService.get_install_command(
        user="root",
        ip="10.0.0.10",
        node_id=f"node-{install_mode}",
        os=NodeConstants.LINUX_OS,
        package_id=str(package.id),
        cloud_region_id=str(cloud_region.id),
        organizations=[],
        node_name=f"node-{install_mode}",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        install_mode=install_mode,
    )
    token = re.search(r"linux_bootstrap\?token=([0-9a-f-]+)", command).group(1)
    usage_key = (
        f"{InstallerConstants.INSTALL_TOKEN_CACHE_PREFIX}:{token}:"
        f"{InstallTokenService.USAGE_COUNT_CACHE_SUFFIX}"
    )

    assert cache.get(usage_key) in (None, 0)

    request = APIRequestFactory().get("/node_mgmt/open_api/installer/session", {"token": token})
    response = OpenSidecarViewSet.as_view({"get": "installer_session"})(request)

    assert response.status_code == 200
    assert cache.get(usage_key) == 1
