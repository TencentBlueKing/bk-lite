import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.utils.permission import authorize_target_organizations
from apps.node_mgmt.views.installer import InstallerViewSet
from apps.system_mgmt.utils.group_utils import GroupUtils


def _build_admin_user():
    return User(
        username="installer-authorization-test-user",
        domain="domain.com",
        locale="en",
        is_superuser=True,
        roles=["admin"],
        group_list=[{"id": 1, "name": "Team"}],
    )


def _build_regular_user():
    return User(
        username="installer-authorization-regular-user",
        domain="domain.com",
        locale="en",
        is_superuser=False,
        roles=[],
        group_list=[{"id": 1, "name": "Team"}],
    )


def _deny_target_organizations(monkeypatch):
    captured = {}

    def deny(request, node, organizations):
        captured["organizations"] = organizations
        return WebUtils.response_403("denied")

    monkeypatch.setattr(
        "apps.node_mgmt.views.installer.authorize_target_organizations",
        deny,
        raising=False,
    )
    return captured


def test_target_organization_authorization_normalizes_dict_group_list(monkeypatch):
    captured = {}

    def get_descendants(group_ids):
        captured["group_ids"] = group_ids
        return [1, 2]

    monkeypatch.setattr(GroupUtils, "get_group_with_descendants", staticmethod(get_descendants))
    request = APIRequestFactory().post("/node_mgmt/api/installer/controller/install/", {}, format="json")
    force_authenticate(request, user=_build_regular_user())

    response = authorize_target_organizations(request, None, [2])

    assert response is None
    assert captured["group_ids"] == [1]


@pytest.mark.django_db
def test_get_install_command_rejects_unauthorized_target_organizations(monkeypatch):
    captured = _deny_target_organizations(monkeypatch)
    monkeypatch.setattr(
        InstallerService,
        "get_install_command",
        lambda *args, **kwargs: pytest.fail("install command must not be issued"),
    )
    request = APIRequestFactory().post(
        "/node_mgmt/api/installer/get_install_command/",
        {
            "ip": "10.0.0.31",
            "node_id": "node-31",
            "os": "linux",
            "package_id": 1,
            "cloud_region_id": 1,
            "organizations": [99],
            "node_name": "node-31",
            "cpu_architecture": "x86_64",
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = InstallerViewSet.as_view({"post": "get_install_command"})(request)

    assert response.status_code == 403
    assert captured["organizations"] == [99]


@pytest.mark.django_db
def test_controller_manual_install_rejects_unauthorized_target_organizations(monkeypatch):
    captured = _deny_target_organizations(monkeypatch)
    request = APIRequestFactory().post(
        "/node_mgmt/api/installer/controller/manual_install/",
        {
            "cloud_region_id": 1,
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": "x86_64",
            "package_id": 1,
            "nodes": [
                {
                    "ip": "10.0.0.13",
                    "node_id": "node-13",
                    "node_name": "linux-node",
                    "organizations": [99],
                }
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = InstallerViewSet.as_view({"post": "controller_manual_install"})(request)

    assert response.status_code == 403
    assert captured["organizations"] == [99]


@pytest.mark.django_db
def test_controller_install_rejects_unauthorized_target_organizations(monkeypatch):
    captured = _deny_target_organizations(monkeypatch)
    monkeypatch.setattr(
        InstallerService,
        "install_controller",
        lambda *args, **kwargs: pytest.fail("install task must not be created"),
    )
    request = APIRequestFactory().post(
        "/node_mgmt/api/installer/controller/install/",
        {
            "cloud_region_id": 1,
            "work_node": "worker-1",
            "package_id": 1,
            "cpu_architecture": "x86_64",
            "nodes": [
                {
                    "ip": "10.0.0.41",
                    "node_name": "linux-node",
                    "os": NodeConstants.LINUX_OS,
                    "organizations": [99],
                    "port": 22,
                    "username": "root",
                    "password": "secret",
                    "private_key": "",
                    "passphrase": "",
                },
                {
                    "ip": "10.0.0.42",
                    "node_name": "second-linux-node",
                    "os": NodeConstants.LINUX_OS,
                    "organizations": [100],
                    "port": 22,
                    "username": "root",
                    "password": "secret",
                    "private_key": "",
                    "passphrase": "",
                }
            ],
        },
        format="json",
    )
    force_authenticate(request, user=_build_admin_user())

    response = InstallerViewSet.as_view({"post": "controller_install"})(request)

    assert response.status_code == 403
    assert captured["organizations"] == [99, 100]
