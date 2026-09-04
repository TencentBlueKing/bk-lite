"""控制器远程安装 NATS 入口：参数校验、组织范围与任务派发。"""

from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node, NodeOrganization, PackageVersion
from apps.node_mgmt.models.installer import ControllerTask, ControllerTaskNode
from apps.node_mgmt.nats import node as n

pytestmark = pytest.mark.django_db


def _region():
    return CloudRegion.objects.create(name="nats-ctrl-install", introduction="", created_by="tester", updated_by="tester")


def _package():
    return PackageVersion.objects.create(
        type="controller",
        os=NodeConstants.LINUX_OS,
        cpu_architecture=NodeConstants.X86_64_ARCH,
        object="Controller",
        version="nats-remote-install",
        name="controller-linux",
    )


def _payload(region_id, package_id, **node_over):
    node = {
        "ip": "10.8.8.10",
        "node_name": "remote-linux",
        "os": NodeConstants.LINUX_OS,
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "organizations": [1],
        "port": 22,
        "username": "root",
        "password": "super-secret",
    }
    node.update(node_over)
    return {
        "cloud_region_id": region_id,
        "work_node": "executor-1",
        "package_id": package_id,
        "cpu_architecture": NodeConstants.X86_64_ARCH,
        "nodes": [node],
    }


def test_install_controller_nats_creates_task_and_dispatches_worker(monkeypatch):
    region = _region()
    package = _package()
    delayed = []
    monkeypatch.setattr(n, "install_controller_task", SimpleNamespace(delay=delayed.append))

    result = n.install_controller(_payload(region.id, package.id), [1])

    task = ControllerTask.objects.get(id=result["task_id"])
    node = ControllerTaskNode.objects.get(task=task)
    assert result == {"task_id": task.id}
    assert delayed == [task.id]
    assert task.type == "install"
    assert node.ip == "10.8.8.10"
    assert node.password != "super-secret"
    assert node.username == "root"


def test_install_controller_nats_log_does_not_leak_credentials(caplog, monkeypatch):
    region = _region()
    package = _package()
    monkeypatch.setattr(n, "install_controller_task", SimpleNamespace(delay=lambda task_id: None))
    caplog.set_level("INFO", logger="node")

    result = n.install_controller(_payload(region.id, package.id), [1])

    records = [record for record in caplog.records if record.msg == "event=nats_install_controller_accepted task_id=%s"]
    assert len(records) == 1
    assert records[0].args == (result["task_id"],)
    assert records[0].getMessage() == f"event=nats_install_controller_accepted task_id={result['task_id']}"
    assert "super-secret" not in caplog.text


@pytest.mark.parametrize(
    "data, organization_ids, match",
    [
        ("bad", [1], "data 必须是对象"),
        ({"created_by": "admin"}, [1], "不允许通过消息参数覆盖安装身份或组织范围"),
        ({"organization_ids": [1]}, [1], "不允许通过消息参数覆盖安装身份或组织范围"),
        ({}, None, "organization_ids 必须是组织 ID 列表"),
        ({}, [], "organization_ids 参数不能为空"),
        ({}, ["bad"], "organization_ids 参数非法"),
    ],
)
def test_install_controller_nats_rejects_untrusted_identity(data, organization_ids, match):
    with pytest.raises(BaseAppException, match=match):
        n.install_controller(data, organization_ids)
    assert ControllerTask.objects.exists() is False


def test_install_controller_nats_rejects_invalid_remote_payload():
    region = _region()
    package = _package()
    payload = _payload(region.id, package.id)
    payload["nodes"][0]["username"] = ""

    with pytest.raises(BaseAppException, match="控制器远程安装参数不合法"):
        n.install_controller(payload, [1])
    assert ControllerTask.objects.exists() is False


def test_install_controller_nats_rejects_unassignable_org_without_side_effects(monkeypatch):
    region = _region()
    package = _package()
    delayed = []
    monkeypatch.setattr(n, "install_controller_task", SimpleNamespace(delay=delayed.append))

    with pytest.raises(BaseAppException, match="目标组织不在授权范围内"):
        n.install_controller(_payload(region.id, package.id, organizations=[2]), [1])

    assert delayed == []
    assert ControllerTask.objects.exists() is False


def test_install_controller_nats_rejects_existing_node_outside_scope(monkeypatch):
    region = _region()
    package = _package()
    outsider = Node.objects.create(
        id="nats-ctrl-outsider",
        name="nats-ctrl-outsider",
        ip="10.8.8.2",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        created_by="tester",
        updated_by="tester",
    )
    NodeOrganization.objects.create(node=outsider, organization=2)
    delayed = []
    monkeypatch.setattr(n, "install_controller_task", SimpleNamespace(delay=delayed.append))

    with pytest.raises(BaseAppException, match="无权在指定节点上安装控制器"):
        n.install_controller(
            _payload(region.id, package.id, node_id=outsider.id, ip="10.8.8.99"),
            [1],
        )

    assert delayed == []
    assert ControllerTask.objects.exists() is False


def test_install_controller_nats_allows_new_node_id_before_registration(monkeypatch):
    region = _region()
    package = _package()
    delayed = []
    monkeypatch.setattr(n, "install_controller_task", SimpleNamespace(delay=delayed.append))

    result = n.install_controller(
        _payload(region.id, package.id, node_id="nats-ctrl-new-node"),
        [1],
    )

    node = ControllerTaskNode.objects.get(task_id=result["task_id"])
    assert node.node_id == "nats-ctrl-new-node"
    assert delayed == [result["task_id"]]
    assert Node.objects.filter(id="nats-ctrl-new-node").exists() is False
