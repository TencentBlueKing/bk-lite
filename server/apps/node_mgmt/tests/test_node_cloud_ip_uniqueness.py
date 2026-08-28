"""(cloud_region, ip) business uniqueness: install/import reject occupied IPs.

No schema UniqueConstraint is added. Historical duplicate Node rows stay as they are.
"""

import logging
from types import SimpleNamespace

import pytest
from django.db.models import UniqueConstraint

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node
from apps.node_mgmt.models.installer import ControllerTaskNode
from apps.node_mgmt.serializers.installer import ControllerInstallRequestSerializer, InstallCommandRequestSerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.node_identity import (
    assert_cloud_ips_available,
    cloud_ip_already_exists_message,
    duplicate_ip_in_batch_message,
)
from apps.node_mgmt.services.sidecar import Sidecar

pytestmark = [pytest.mark.django_db]


def _create_node(region, ip, node_id, **overrides):
    values = {
        "id": node_id,
        "name": node_id,
        "ip": ip,
        "operating_system": NodeConstants.LINUX_OS,
        "collector_configuration_directory": "/etc/collector",
        "cloud_region": region,
    }
    values.update(overrides)
    return Node.objects.create(**values)


def _install_payload(ip, **overrides):
    node = {
        "ip": ip,
        "node_name": f"host-{ip}",
        "os": NodeConstants.LINUX_OS,
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "organizations": [1],
        "port": 22,
        "username": "root",
        "password": "secret",
        "private_key": "",
        "passphrase": "",
    }
    node.update(overrides)
    return node


def _heartbeat_request(node_name, node_details):
    return SimpleNamespace(headers={}, META={}, data={"node_name": node_name, "node_details": node_details})


def _node_details(region_id, ip, **overrides):
    details = {
        "ip": ip,
        "operating_system": "Linux",
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "collector_configuration_directory": "/opt/fusion-collectors/generated",
        "metrics": {"cpu": 30},
        "status": {"status": 0},
        "tags": [
            f"zone:{region_id}",
            f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
            f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
        ],
        "log_file_list": [],
    }
    details.update(overrides)
    return details


def test_install_batch_rejects_duplicate_ips_in_same_cloud_region():
    region = CloudRegion.objects.create(name="uniqueness-dup-batch")
    with pytest.raises(ValidationAppException, match="10.0.0.1 is duplicated"):
        assert_cloud_ips_available(
            region.id,
            [_install_payload("10.0.0.1"), _install_payload("10.0.0.1")],
        )


def test_install_serializer_rejects_duplicate_ips_in_same_request():
    region = CloudRegion.objects.create(name="uniqueness-serializer-dup")
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": region.id,
            "work_node": "work-1",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [_install_payload("10.0.0.1"), _install_payload("10.0.0.1")],
        }
    )
    assert serializer.is_valid() is False
    assert duplicate_ip_in_batch_message("10.0.0.1") in str(serializer.errors)


def test_same_ip_allowed_in_different_cloud_regions():
    region_a = CloudRegion.objects.create(name="uniqueness-region-a")
    region_b = CloudRegion.objects.create(name="uniqueness-region-b")
    _create_node(region_a, "10.0.0.9", "node-region-a")

    assert_cloud_ips_available(region_b.id, [_install_payload("10.0.0.9")])

    task_id = InstallerService.install_controller(
        region_b.id,
        "work-1",
        5,
        [_install_payload("10.0.0.9")],
        NodeConstants.X86_64_ARCH,
    )
    task_node = ControllerTaskNode.objects.get(task_id=task_id)
    assert task_node.ip == "10.0.0.9"
    assert task_node.node_id == ""
    assert Node.objects.filter(ip="10.0.0.9").count() == 1


def test_install_existing_ip_is_rejected():
    region = CloudRegion.objects.create(name="uniqueness-existing-as-new")
    _create_node(region, "10.0.0.4", "existing-node-4")

    with pytest.raises(ValidationAppException, match=cloud_ip_already_exists_message("10.0.0.4")):
        InstallerService.install_controller(
            region.id,
            "work-1",
            5,
            [_install_payload("10.0.0.4")],
            NodeConstants.X86_64_ARCH,
        )

    assert not ControllerTaskNode.objects.filter(ip="10.0.0.4").exists()
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.4").count() == 1


def test_install_serializer_rejects_ip_already_in_cloud_region():
    region = CloudRegion.objects.create(name="uniqueness-serializer-exists")
    _create_node(region, "10.0.0.4", "existing-node-4")
    serializer = ControllerInstallRequestSerializer(
        data={
            "cloud_region_id": region.id,
            "work_node": "work-1",
            "package_id": 1,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "nodes": [_install_payload("10.0.0.4")],
        }
    )
    assert serializer.is_valid() is False
    assert cloud_ip_already_exists_message("10.0.0.4") in str(serializer.errors)


def test_install_command_rejects_ip_already_in_cloud_region():
    region = CloudRegion.objects.create(name="uniqueness-command-exists")
    _create_node(region, "10.0.0.4", "existing-node-4")
    serializer = InstallCommandRequestSerializer(
        data={
            "ip": "10.0.0.4",
            "node_id": "brand-new-node-id",
            "os": NodeConstants.LINUX_OS,
            "cpu_architecture": NodeConstants.X86_64_ARCH,
            "package_id": 1,
            "cloud_region_id": region.id,
            "organizations": [1],
        }
    )
    assert serializer.is_valid() is False
    assert cloud_ip_already_exists_message("10.0.0.4") in str(serializer.errors)


def test_sidecar_create_rejects_existing_cloud_ip(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="uniqueness-sidecar-reject")
    existing = _create_node(region, "10.0.0.6", "existing-node-6")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: pytest.fail("must not create"))
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="node")

    with pytest.raises(ValidationAppException, match=cloud_ip_already_exists_message("10.0.0.6")) as raised:
        Sidecar.update_node_client(
            _heartbeat_request("new-sidecar", _node_details(region.id, "10.0.0.6")),
            "brand-new-node-id",
        )

    assert raised.value.message == cloud_ip_already_exists_message("10.0.0.6")
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.6").count() == 1
    assert not Node.objects.filter(id="brand-new-node-id").exists()
    existing.refresh_from_db()
    assert existing.id == "existing-node-6"
    assert existing.ip == "10.0.0.6"
    assert not any(record.name == "node" and record.exc_info for record in caplog.records)
    assert not any(
        record.name == "node" and "sidecar_create_duplicate_cloud_ip" in (record.msg or "")
        for record in caplog.records
    )


def test_sidecar_create_allows_same_ip_in_different_cloud_region(monkeypatch, caplog):
    region_a = CloudRegion.objects.create(name="uniqueness-sidecar-a")
    region_b = CloudRegion.objects.create(name="uniqueness-sidecar-b")
    _create_node(region_a, "10.0.0.7", "node-in-a")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="node")

    response = Sidecar.update_node_client(
        _heartbeat_request("node-in-b", _node_details(region_b.id, "10.0.0.7")),
        "node-in-b",
    )

    assert response.status_code == 202
    assert Node.objects.filter(ip="10.0.0.7").count() == 2
    assert Node.objects.get(id="node-in-b").cloud_region_id == region_b.id
    assert not any(record.name == "node" and record.levelno >= logging.INFO for record in caplog.records)


def test_historical_duplicate_nodes_remain_and_third_create_is_blocked(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="uniqueness-historical")
    first = _create_node(region, "10.0.0.8", "historical-one")
    second = _create_node(region, "10.0.0.8", "historical-two")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: pytest.fail("must not create"))
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="node")

    with pytest.raises(ValidationAppException, match=cloud_ip_already_exists_message("10.0.0.8")) as raised:
        Sidecar.update_node_client(
            _heartbeat_request("third", _node_details(region.id, "10.0.0.8")),
            "historical-three",
        )

    assert raised.value.message == cloud_ip_already_exists_message("10.0.0.8")
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.8").count() == 2
    assert Node.objects.filter(id=first.id).exists()
    assert Node.objects.filter(id=second.id).exists()
    assert not Node.objects.filter(id="historical-three").exists()
    assert not any(record.name == "node" and record.exc_info for record in caplog.records)
    assert not any(
        record.name == "node" and "sidecar_create_duplicate_cloud_ip" in (record.msg or "")
        for record in caplog.records
    )

    with pytest.raises(ValidationAppException, match=cloud_ip_already_exists_message("10.0.0.8")):
        assert_cloud_ips_available(region.id, [_install_payload("10.0.0.8")])


def test_node_model_has_no_cloud_ip_schema_uniqueness():
    unique_together = getattr(Node._meta, "unique_together", ())
    assert ("cloud_region", "ip") not in unique_together
    assert ("ip", "cloud_region") not in unique_together
    for constraint in Node._meta.constraints:
        if isinstance(constraint, UniqueConstraint):
            assert tuple(constraint.fields) not in {("cloud_region", "ip"), ("ip", "cloud_region")}
    field_names = {field.name for field in Node._meta.fields if getattr(field, "unique", False)}
    assert "ip" not in field_names


def test_heartbeat_ip_rewrite_still_updates_when_target_ip_is_free(monkeypatch):
    region = CloudRegion.objects.create(name="uniqueness-heartbeat-rewrite")
    node = _create_node(region, "10.0.0.10", "rewrite-node")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request(node.name, _node_details(region.id, "10.0.0.20")),
        node.id,
    )

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.ip == "10.0.0.20"
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.20").count() == 1
    assert Node.objects.filter(id=node.id).count() == 1


def test_existing_heartbeat_ignores_invalid_zone_tag(monkeypatch):
    region = CloudRegion.objects.create(name="uniqueness-invalid-zone")
    node = _create_node(region, "10.0.0.11", "zone-node")
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    details = _node_details(region.id, "10.0.0.11")
    details["tags"] = [
        "zone:not-an-id",
        f"{ControllerConstants.INSTALL_METHOD_TAG}:{ControllerConstants.MANUAL}",
        f"{ControllerConstants.NODE_TYPE_TAG}:{ControllerConstants.NODE_TYPE_HOST}",
    ]

    response = Sidecar.update_node_client(_heartbeat_request(node.name, details), node.id)

    node.refresh_from_db()
    assert response.status_code == 202
    assert node.cloud_region_id == region.id
    assert node.ip == "10.0.0.11"
