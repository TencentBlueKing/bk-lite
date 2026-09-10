"""Node.ip identity: install target wins on first register; hosts freeze; containers update."""

from types import SimpleNamespace

import pytest

from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.services.sidecar import Sidecar

pytestmark = [pytest.mark.django_db]


def _heartbeat_request(node_name, node_details, etag=None):
    headers = {}
    if etag:
        headers["If-None-Match"] = f'"{etag}"'
    return SimpleNamespace(headers=headers, META={}, data={"node_name": node_name, "node_details": node_details})


def _node_details(region_id, ip, **overrides):
    details = {
        "ip": ip,
        "operating_system": "Linux",
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "collector_configuration_directory": "/opt/fusion-collectors/generated",
        "metrics": {},
        "status": {"status": 0},
        "tags": [
            f"zone:{region_id}",
            f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.AUTO}",
            f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
        ],
        "log_file_list": [],
    }
    details.update(overrides)
    return details


def _create_region(name):
    return CloudRegion.objects.create(name=name, introduction="test", created_by="tester", updated_by="tester")


def _create_node(region, ip, node_id, **overrides):
    values = {
        "id": node_id,
        "name": node_id,
        "ip": ip,
        "operating_system": NodeConstants.LINUX_OS,
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "collector_configuration_directory": "/opt/fusion-collectors/generated",
        "cloud_region": region,
        "node_type": ControllerConstants.NODE_TYPE_HOST,
    }
    values.update(overrides)
    return Node.objects.create(**values)


def _create_install_task(region, node_id, ip, **overrides):
    task = ControllerTask.objects.create(
        type="install",
        package_version_id=1,
        status="running",
        cloud_region=region,
        work_node="worker-1",
        created_by="tester",
        updated_by="tester",
    )
    values = {
        "task": task,
        "ip": ip,
        "os": NodeConstants.LINUX_OS,
        "port": 22,
        "username": "root",
        "password": "",
        "status": "running",
        "result": {InstallerConstants.INSTALL_NODE_ID_KEY: node_id},
        "cpu_architecture": NodeConstants.X86_64_ARCH,
    }
    values.update(overrides)
    return ControllerTaskNode.objects.create(**values)


def test_first_register_uses_install_target_ip_instead_of_sidecar_nic(monkeypatch):
    region = _create_region("identity-first-install")
    _create_install_task(region, "bond-host", "10.0.0.10")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request("bond-host", _node_details(region.id, "10.0.1.8")),
        "bond-host",
    )

    assert response.status_code == 202
    assert Node.objects.get(id="bond-host").ip == "10.0.0.10"


def test_first_register_falls_back_to_sidecar_ip_without_install_task(monkeypatch):
    region = _create_region("identity-first-manual")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request("manual-host", _node_details(region.id, "10.0.1.8")),
        "manual-host",
    )

    assert response.status_code == 202
    assert Node.objects.get(id="manual-host").ip == "10.0.1.8"


def test_host_heartbeat_does_not_accept_sidecar_ip_overwrite(monkeypatch):
    region = _create_region("identity-host-freeze")
    node = _create_node(region, "10.0.0.10", "frozen-host")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.1.8")),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.ip == "10.0.0.10"


def test_host_heartbeat_corrects_ip_from_install_task(monkeypatch):
    region = _create_region("identity-host-correct")
    node = _create_node(region, "10.0.1.8", "wrong-eth-host")
    _create_install_task(region, node.id, "10.0.0.10")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.1.8")),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.ip == "10.0.0.10"


def test_host_heartbeat_keeps_ip_when_install_correction_conflicts(monkeypatch):
    region = _create_region("identity-host-conflict")
    node = _create_node(region, "10.0.1.8", "conflict-host")
    _create_node(region, "10.0.0.10", "other-host")
    _create_install_task(region, node.id, "10.0.0.10")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.1.8")),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.ip == "10.0.1.8"


def test_host_ignores_container_tag_when_deciding_ip_update(monkeypatch):
    region = _create_region("identity-host-tag")
    node = _create_node(region, "10.0.0.10", "tag-host")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    details = _node_details(
        region.id,
        "10.0.1.8",
        tags=[
            f"zone:{region.id}",
            f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
        ],
    )

    Sidecar.update_node_client(_heartbeat_request(node.name, details), node.id)

    node.refresh_from_db()
    assert node.ip == "10.0.0.10"
    assert node.node_type == ControllerConstants.NODE_TYPE_CONTAINER


def test_container_heartbeat_updates_ip_from_sidecar(monkeypatch):
    region = _create_region("identity-container-update")
    node = _create_node(
        region,
        "10.0.0.1",
        "container-node",
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    details = _node_details(
        region.id,
        "10.0.0.2",
        tags=[
            f"zone:{region.id}",
            f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_CONTAINER}",
        ],
    )

    response = Sidecar.update_node_client(_heartbeat_request(node.name, details), node.id)

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.ip == "10.0.0.2"


def test_container_heartbeat_ignores_install_target_after_register(monkeypatch):
    region = _create_region("identity-container-install")
    node = _create_node(
        region,
        "10.0.0.1",
        "container-with-task",
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    _create_install_task(region, node.id, "10.0.0.10")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.0.2")),
        node.id,
    )

    node.refresh_from_db()
    assert node.ip == "10.0.0.2"


def test_cached_host_heartbeat_does_not_accept_sidecar_ip_overwrite(monkeypatch):
    region = _create_region("identity-cached-host")
    node = _create_node(region, "10.0.0.10", "cached-host")
    monkeypatch.setattr("apps.node_mgmt.services.sidecar.cache.get", lambda _key: "cached-etag")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.1.8"), etag="cached-etag"),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 304
    assert node.ip == "10.0.0.10"


def test_cached_host_heartbeat_corrects_ip_from_install_task(monkeypatch):
    region = _create_region("identity-cached-correct")
    node = _create_node(region, "10.0.1.8", "cached-wrong-host")
    _create_install_task(region, node.id, "10.0.0.10")
    monkeypatch.setattr("apps.node_mgmt.services.sidecar.cache.get", lambda _key: "cached-etag")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.1.8"), etag="cached-etag"),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 304
    assert node.ip == "10.0.0.10"


def test_cached_container_heartbeat_updates_ip_from_sidecar(monkeypatch):
    region = _create_region("identity-cached-container")
    node = _create_node(
        region,
        "10.0.0.1",
        "cached-container",
        node_type=ControllerConstants.NODE_TYPE_CONTAINER,
    )
    monkeypatch.setattr("apps.node_mgmt.services.sidecar.cache.get", lambda _key: "cached-etag")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.0.2"), etag="cached-etag"),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 304
    assert node.ip == "10.0.0.2"


def test_unusable_install_target_ip_is_ignored_on_first_register(monkeypatch):
    region = _create_region("identity-unusable-install")
    _create_install_task(region, "apipa-host", "169.254.1.5")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    Sidecar.update_node_client(
        _heartbeat_request("apipa-host", _node_details(region.id, "10.0.1.8")),
        "apipa-host",
    )

    assert Node.objects.get(id="apipa-host").ip == "10.0.1.8"
