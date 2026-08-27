"""(cloud_region, ip) business uniqueness: import/install reuse, sidecar create, historical duplicates.

No schema UniqueConstraint is added. Historical duplicate Node rows stay as they are.
"""

import logging
from queue import Queue
from types import SimpleNamespace

import pytest
from django.db.models import UniqueConstraint

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.constants.installer import InstallerConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node, PackageVersion
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.serializers.installer import ControllerInstallRequestSerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.services.node_identity import bind_existing_cloud_ip_node_ids, cloud_ip_already_exists_message, duplicate_ip_in_batch_message
from apps.node_mgmt.services.sidecar import Sidecar
from apps.node_mgmt.tasks import installer as installer_tasks

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


def _stub_install_execution(monkeypatch):
    install_call = {}

    def fake_get_install_command(*args, **kwargs):
        install_call["args"] = args
        install_call["kwargs"] = kwargs
        return "echo install"

    monkeypatch.setattr(installer_tasks, "exec_command_to_remote", lambda *args, **kwargs: "x86_64")
    monkeypatch.setattr(installer_tasks, "exec_command_to_remote_stream", lambda *args, **kwargs: "")
    monkeypatch.setattr(installer_tasks, "subscribe_lines_sync", lambda *args, **kwargs: (Queue(), lambda: None))
    monkeypatch.setattr(installer_tasks.InstallerService, "get_install_command", fake_get_install_command)
    monkeypatch.setattr(installer_tasks, "_dispatch_or_finalize_controller_task", lambda task_id: None)
    return install_call


def test_install_batch_rejects_duplicate_ips_in_same_cloud_region():
    region = CloudRegion.objects.create(name="uniqueness-dup-batch")
    with pytest.raises(ValidationAppException, match="10.0.0.1 is duplicated"):
        bind_existing_cloud_ip_node_ids(
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

    bound = bind_existing_cloud_ip_node_ids(region_b.id, [_install_payload("10.0.0.9")])
    assert bound[0].get("node_id") in (None, "")

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


def test_install_existing_ip_as_new_reuses_existing_node_id():
    region = CloudRegion.objects.create(name="uniqueness-existing-as-new")
    existing = _create_node(region, "10.0.0.4", "existing-node-4")

    task_id = InstallerService.install_controller(
        region.id,
        "work-1",
        5,
        [_install_payload("10.0.0.4")],
        NodeConstants.X86_64_ARCH,
    )
    task_node = ControllerTaskNode.objects.get(task_id=task_id)
    assert task_node.node_id == existing.id
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.4").count() == 1


def test_reinstall_reuses_existing_node_id_in_installer_payload(monkeypatch):
    region = CloudRegion.objects.create(name="uniqueness-reinstall")
    existing = _create_node(region, "10.0.0.5", "existing-node-5")
    package = PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="uniqueness-reinstall",
        name="controller-linux",
    )
    task = ControllerTask.objects.create(
        cloud_region=region,
        type="install",
        status="waiting",
        work_node="work-1",
        package_version_id=package.id,
    )
    aes = AESCryptor()
    task_node = ControllerTaskNode.objects.create(
        task=task,
        ip="10.0.0.5",
        node_name="reinstall-host",
        os=NodeConstants.LINUX_OS,
        organizations=[1],
        port=22,
        username="root",
        password=aes.encode("secret"),
        status="waiting",
        cpu_architecture=NodeConstants.X86_64_ARCH,
    )
    install_call = _stub_install_execution(monkeypatch)

    installer_tasks.install_controller_on_nodes(task, [task_node], package)
    task_node.refresh_from_db()

    assert install_call["args"][2] == existing.id
    assert task_node.node_id == existing.id
    assert task_node.result[InstallerConstants.INSTALL_NODE_ID_KEY] == existing.id
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.5").count() == 1


def test_sidecar_create_attaches_to_existing_cloud_ip_instead_of_second_row(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="uniqueness-sidecar-attach")
    existing = _create_node(region, "10.0.0.6", "existing-node-6")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="node")

    response = Sidecar.update_node_client(
        _heartbeat_request("new-sidecar", _node_details(region.id, "10.0.0.6")),
        "brand-new-node-id",
    )

    assert response.status_code == 202
    assert Node.objects.filter(cloud_region=region, ip="10.0.0.6").count() == 1
    assert not Node.objects.filter(id="brand-new-node-id").exists()
    existing.refresh_from_db()
    assert existing.id == "existing-node-6"
    assert existing.ip == "10.0.0.6"
    attach_records = [
        record for record in caplog.records if record.name == "node" and record.msg.startswith("event=sidecar_create_attached_existing_node")
    ]
    assert len(attach_records) == 1
    assert attach_records[0].levelno == logging.INFO
    assert attach_records[0].args == (existing.id, "brand-new-node-id", "10.0.0.6", region.id)
    assert attach_records[0].getMessage() == (
        f"event=sidecar_create_attached_existing_node existing_node_id={existing.id} "
        f"reported_node_id=brand-new-node-id ip=10.0.0.6 cloud_region_id={region.id}"
    )
    assert attach_records[0].exc_info is None


def test_sidecar_create_allows_same_ip_in_different_cloud_region(monkeypatch):
    region_a = CloudRegion.objects.create(name="uniqueness-sidecar-a")
    region_b = CloudRegion.objects.create(name="uniqueness-sidecar-b")
    _create_node(region_a, "10.0.0.7", "node-in-a")
    monkeypatch.setattr(Sidecar, "create_default_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(Sidecar, "trigger_converge_tasks_if_needed", lambda *args, **kwargs: None)

    response = Sidecar.update_node_client(
        _heartbeat_request("node-in-b", _node_details(region_b.id, "10.0.0.7")),
        "node-in-b",
    )

    assert response.status_code == 202
    assert Node.objects.filter(ip="10.0.0.7").count() == 2
    assert Node.objects.get(id="node-in-b").cloud_region_id == region_b.id


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
    reject_records = [
        record for record in caplog.records if record.name == "node" and record.msg.startswith("event=sidecar_create_duplicate_cloud_ip")
    ]
    assert len(reject_records) == 1
    assert reject_records[0].levelno == logging.WARNING
    assert reject_records[0].args == (
        "ValidationAppException",
        "historical-three",
        "10.0.0.8",
        region.id,
    )
    assert reject_records[0].getMessage() == (
        "event=sidecar_create_duplicate_cloud_ip failed_stage=sidecar_create "
        "error_type=ValidationAppException reported_node_id=historical-three "
        f"ip=10.0.0.8 cloud_region_id={region.id}"
    )
    assert reject_records[0].exc_info is None
    assert not any(record.name == "node" and record.exc_info for record in caplog.records)

    with pytest.raises(ValidationAppException, match=cloud_ip_already_exists_message("10.0.0.8")):
        bind_existing_cloud_ip_node_ids(region.id, [_install_payload("10.0.0.8")])


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
