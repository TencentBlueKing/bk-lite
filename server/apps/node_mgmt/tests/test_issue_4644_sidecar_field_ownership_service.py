import logging
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node
from apps.node_mgmt.services.sidecar import Sidecar

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _heartbeat_request(node_name, node_details):
    return SimpleNamespace(headers={}, META={}, data={"node_name": node_name, "node_details": node_details})


def _node_details(region_id, **overrides):
    details = {
        "ip": "10.0.0.20",
        "operating_system": "Linux",
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "collector_configuration_directory": "/opt/fusion-collectors/generated",
        "metrics": {"cpu": 30},
        "status": {"status": 0},
        "tags": [
            f"zone:{region_id}",
            f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
            f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
        ],
        "log_file_list": ["/var/log/app.log"],
    }
    details.update(overrides)
    return details


def test_existing_sidecar_heartbeat_preserves_server_owned_fields(monkeypatch, caplog):
    original_region = CloudRegion.objects.create(name="issue-4644-original")
    reported_region = CloudRegion.objects.create(name="issue-4644-reported")
    node = Node.objects.create(
        id="issue-4644-existing",
        name="server-owned-name",
        ip="10.0.0.10",
        operating_system=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        collector_configuration_directory="/etc/collector",
        metrics={},
        status={},
        tags=[],
        log_file_list=[],
        cloud_region=original_region,
        cmdb_id="cmdb-server",
        monitor_id="monitor-server",
        push_status={"cmdb": {"state": "ok"}},
        created_by="server-admin",
        updated_by="server-admin",
    )
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.WARNING)

    request = _heartbeat_request(
        "untrusted-name",
        _node_details(
            reported_region.id,
            cloud_region_id=reported_region.id,
            cmdb_id="cmdb-untrusted",
            monitor_id="monitor-untrusted",
            push_status={"monitor": {"state": "done"}},
            created_by="untrusted-creator",
            updated_by="untrusted-updater",
        ),
    )

    response = Sidecar.update_node_client(request, node.id)

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.name == "server-owned-name"
    assert node.cloud_region_id == original_region.id
    assert node.cmdb_id == "cmdb-server"
    assert node.monitor_id == "monitor-server"
    assert node.push_status == {"cmdb": {"state": "ok"}}
    assert node.created_by == "server-admin"
    assert node.updated_by == "server-admin"
    assert node.ip == "10.0.0.10"
    assert node.operating_system == NodeConstants.LINUX_OS
    assert node.collector_configuration_directory == "/opt/fusion-collectors/generated"
    assert node.metrics == {"cpu": 30}
    assert node.status == {"status": 0}
    assert node.tags == [
        f"zone:{reported_region.id}",
        f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
        f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
    ]
    assert node.log_file_list == ["/var/log/app.log"]
    assert node.install_method == ControllerConstants.MANUAL
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER
    assert "cmdb_id" in caplog.text
    assert "cmdb-untrusted" not in caplog.text


def test_cached_heartbeat_ignores_server_owned_and_unknown_fields(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="issue-4644-cached")
    node = Node.objects.create(
        id="issue-4644-cached",
        name="cached-sidecar",
        ip="10.0.0.10",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        cmdb_id="cmdb-server",
    )
    monkeypatch.setattr("apps.node_mgmt.services.sidecar.cache.get", lambda _key: "cached-etag")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.WARNING)

    request = _heartbeat_request(
        node.name,
        {
            "ip": "10.0.0.10",
            "operating_system": "Linux",
            "status": {"status": 1},
            "id": "untrusted-node-id",
            "name": "untrusted-node-name",
            "cmdb_id": "cmdb-untrusted",
            "kernel_version": "6.6.0",
            "forged\nwarning secret-token": "ignored",
            "x" * 10_000: "ignored",
        },
    )
    request.headers = {"If-None-Match": '"cached-etag"'}

    response = Sidecar.update_node_client(request, node.id)

    node.refresh_from_db()
    assert response.status_code == 304
    assert node.cmdb_id == "cmdb-server"
    assert node.status == {"status": 1}
    assert "server_fields=cmdb_id,id,name" in caplog.text
    assert "unknown_field_count=3" in caplog.text
    assert "cmdb-untrusted" not in caplog.text
    assert "untrusted-node-id" not in caplog.text
    assert "untrusted-node-name" not in caplog.text
    assert "forged" not in caplog.text
    assert "secret-token" not in caplog.text
    assert "x" * 100 not in caplog.text


def test_existing_heartbeat_keeps_direct_client_runtime_fields(monkeypatch):
    region = CloudRegion.objects.create(name="issue-4644-direct-runtime-fields")
    node = Node.objects.create(
        id="issue-4644-direct-runtime-fields",
        name="direct-runtime-fields",
        ip="10.0.0.10",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
    )
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(
            node.name,
            _node_details(
                region.id,
                tags=[],
                install_method=ControllerConstants.MANUAL,
                node_type=ControllerConstants.NODE_TYPE_CONTAINER,
            ),
        ),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.install_method == ControllerConstants.MANUAL
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER


def test_first_sidecar_heartbeat_keeps_zone_registration_compatibility(monkeypatch):
    region = CloudRegion.objects.create(name="issue-4644-registration")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(
            "new-sidecar",
            _node_details(
                region.id,
                cmdb_id="cmdb-untrusted",
                monitor_id="monitor-untrusted",
                push_status={"cmdb": {"state": "done"}},
                created_by="untrusted-creator",
            ),
        ),
        "issue-4644-new",
    )

    node = Node.objects.get(id="issue-4644-new")
    assert response.status_code == 202
    assert node.name == "new-sidecar"
    assert node.cloud_region_id == region.id
    assert node.cmdb_id == ""
    assert node.monitor_id == ""
    assert node.push_status == {}
    assert node.created_by == ""
    assert node.install_method == ControllerConstants.MANUAL
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER


@pytest.mark.parametrize("node_details", [None, [], "invalid"])
def test_sidecar_heartbeat_rejects_non_object_node_details(node_details):
    with pytest.raises(ValidationAppException, match="node_details must be an object"):
        Sidecar.update_node_client(_heartbeat_request("invalid", node_details), "issue-4644-invalid")


@pytest.mark.parametrize(
    ("node_details", "message"),
    [
        ({"ip": "10.0.0.1"}, "node_details.operating_system is required"),
        ({"operating_system": 1}, "node_details contains invalid field values"),
        ({"operating_system": "Linux", "tags": "zone:1"}, "node_details contains invalid field values"),
        ({"operating_system": "Linux", "tags": [1]}, "node_details contains invalid field values"),
        ({"operating_system": "Linux", "tags": ["zone:not-an-id"]}, "node_details.tags contains an invalid zone"),
    ],
)
def test_sidecar_heartbeat_rejects_invalid_client_field_values(node_details, message):
    with pytest.raises(ValidationAppException, match=message):
        Sidecar.update_node_client(_heartbeat_request("invalid", node_details), "issue-4644-invalid")
