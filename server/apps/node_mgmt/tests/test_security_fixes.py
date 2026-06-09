# -*- coding: utf-8 -*-
"""
Security Fix Verification Tests (Issues #2878, #2879, #2880)

These tests verify that the security fixes for credential leaks and
organization sync issues are working correctly.
"""
import logging
from types import SimpleNamespace

import pytest

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node, PackageVersion, SidecarEnv
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.services.installer_session import InstallerSessionService
from apps.node_mgmt.services.sidecar import Sidecar


@pytest.mark.django_db
def test_issue_2879_installer_session_prefers_dedicated_credentials(monkeypatch):
    """
    Issue #2879: Verify installer session prefers NATS_INSTALLER_* credentials
    over NATS_ADMIN_* credentials when both are available.
    """
    cloud_region = CloudRegion.objects.create(
        name="test-region-installer-creds",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    # Set up both admin and installer credentials
    SidecarEnv.objects.create(
        key=NodeConstants.SERVER_URL_KEY,
        value="https://example.com",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://127.0.0.1:4222",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key="NATS_ADMIN_USERNAME",
        value="admin_user",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_ADMIN_PASSWORD_KEY,
        value="admin_pass",
        type="text",
        cloud_region=cloud_region,
    )
    # Dedicated installer credentials (should be preferred)
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_USERNAME_KEY,
        value="installer_user",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
        value="installer_pass",
        type="text",
        cloud_region=cloud_region,
    )

    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="test-package.zip",
        created_by="tester",
        updated_by="tester",
    )

    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.InstallTokenService.validate_and_get_token_data",
        lambda token: {
            "package_id": package_obj.id,
            "cloud_region_id": cloud_region.id,
            "ip": "10.0.0.1",
            "user": "admin",
            "node_id": "node-1",
            "node_name": "node-1",
            "os": "linux",
            "remaining_usage": 1,
            "organizations": [],
            "cpu_architecture": NodeConstants.X86_64_ARCH,
        },
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.generate_node_token",
        lambda *args, **kwargs: "sidecar-token",
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda obj: "linux/Controller/1.0.0/test-package.zip",
    )

    config = InstallerSessionService.build_session_config("token")

    # Should use installer credentials, not admin credentials
    assert config["storage"]["nats_username"] == "installer_user"
    assert config["storage"]["nats_password"] == "installer_pass"


@pytest.mark.django_db
def test_issue_2879_installer_session_falls_back_to_admin_credentials(monkeypatch, caplog):
    """
    Issue #2879: Verify installer session falls back to NATS_ADMIN_* credentials
    with a warning when NATS_INSTALLER_* credentials are not configured.
    """
    caplog.set_level(logging.WARNING)

    cloud_region = CloudRegion.objects.create(
        name="test-region-fallback-creds",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    # Only admin credentials, no installer credentials
    SidecarEnv.objects.create(
        key=NodeConstants.SERVER_URL_KEY,
        value="https://example.com",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://127.0.0.1:4222",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key="NATS_ADMIN_USERNAME",
        value="admin_user",
        type="text",
        cloud_region=cloud_region,
    )
    SidecarEnv.objects.create(
        key=NodeConstants.NATS_ADMIN_PASSWORD_KEY,
        value="admin_pass",
        type="text",
        cloud_region=cloud_region,
    )

    package_obj = PackageVersion.objects.create(
        type="controller",
        os="linux",
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="1.0.0",
        name="test-package.zip",
        created_by="tester",
        updated_by="tester",
    )

    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.InstallTokenService.validate_and_get_token_data",
        lambda token: {
            "package_id": package_obj.id,
            "cloud_region_id": cloud_region.id,
            "ip": "10.0.0.1",
            "user": "admin",
            "node_id": "node-1",
            "node_name": "node-1",
            "os": "linux",
            "remaining_usage": 1,
            "organizations": [],
            "cpu_architecture": NodeConstants.X86_64_ARCH,
        },
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.generate_node_token",
        lambda *args, **kwargs: "sidecar-token",
    )
    monkeypatch.setattr(
        "apps.node_mgmt.services.installer_session.PackageService.resolve_existing_file_path",
        lambda obj: "linux/Controller/1.0.0/test-package.zip",
    )

    config = InstallerSessionService.build_session_config("token")

    # Should fall back to admin credentials
    assert config["storage"]["nats_username"] == "admin_user"
    assert config["storage"]["nats_password"] == "admin_pass"
    # Should log a warning about fallback
    assert any("NATS_INSTALLER_USERNAME/PASSWORD not configured" in record.message for record in caplog.records)


@pytest.mark.django_db
def test_issue_2878_sync_groups_incremental_add():
    """
    Issue #2878: Verify sync_groups adds new organizations without removing existing ones.
    """
    cloud_region = CloudRegion.objects.create(
        name="test-region-sync-add",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sync-add",
        name="node-sync-add",
        ip="10.0.0.1",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    # Pre-existing organization
    NodeOrganization.objects.create(node_id=node.id, organization=1)

    # Sync with existing + new organization
    Sidecar.sync_groups(node.id, [1, 2, 3])

    orgs = set(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == {1, 2, 3}


@pytest.mark.django_db
def test_issue_2878_sync_groups_incremental_remove():
    """
    Issue #2878: Verify sync_groups removes organizations no longer in the expected list.
    """
    cloud_region = CloudRegion.objects.create(
        name="test-region-sync-remove",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sync-remove",
        name="node-sync-remove",
        ip="10.0.0.2",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    # Pre-existing organizations
    NodeOrganization.objects.create(node_id=node.id, organization=1)
    NodeOrganization.objects.create(node_id=node.id, organization=2)
    NodeOrganization.objects.create(node_id=node.id, organization=3)

    # Sync with only org 2 (should remove 1 and 3)
    Sidecar.sync_groups(node.id, [2])

    orgs = set(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == {2}


@pytest.mark.django_db
def test_issue_2878_sync_groups_empty_removes_all():
    """
    Issue #2878: Verify sync_groups with empty list removes all organizations.
    """
    cloud_region = CloudRegion.objects.create(
        name="test-region-sync-empty",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-sync-empty",
        name="node-sync-empty",
        ip="10.0.0.3",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    # Pre-existing organizations
    NodeOrganization.objects.create(node_id=node.id, organization=1)
    NodeOrganization.objects.create(node_id=node.id, organization=2)

    # Sync with empty list
    Sidecar.sync_groups(node.id, [])

    orgs = list(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == []


@pytest.mark.django_db
def test_sidecar_heartbeat_does_not_rollback_user_updated_node_organizations(monkeypatch):
    """
    A node management page edit is authoritative for existing nodes.
    A later sidecar heartbeat may still carry stale group tags from the old
    local sidecar.yaml; that heartbeat must not rollback the DB association.
    """
    cloud_region = CloudRegion.objects.create(
        name="test-region-user-org-edit",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    node = Node.objects.create(
        id="node-user-org-edit",
        name="node-user-org-edit",
        ip="10.0.0.4",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=cloud_region,
        created_by="tester",
        updated_by="tester",
    )
    NodeOrganization.objects.create(node_id=node.id, organization=2)

    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    request = SimpleNamespace(
        headers={},
        META={},
        data={
            "node_name": "node-user-org-edit",
            "node_details": {
                "ip": "10.0.0.4",
                "operating_system": "Linux",
                "collector_configuration_directory": "/etc/collector",
                "metrics": {},
                "status": {},
                "tags": [f"zone:{cloud_region.id}", "group:1"],
                "log_file_list": [],
            },
        },
    )

    response = Sidecar.update_node_client(request, node.id)

    assert response.status_code == 202
    orgs = set(NodeOrganization.objects.filter(node_id=node.id).values_list("organization", flat=True))
    assert orgs == {2}
