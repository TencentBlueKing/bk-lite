import base64
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "support-files/vmware/provision_vm.py"
spec = importlib.util.spec_from_file_location("provision_vm", SCRIPT)
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)

REQUEST = dict(
    vc_host="vc.invalid",
    delivery_id="REQ42-1",
    profile="test",
    template_id="vm-7",
    cpu=2,
    memory_gib=4,
    data_disk_gib=20,
    network_id="network-8",
    disk_policy_id="standard",
)


class FakeCenter:
    def __init__(self):
        self.submitted = 0
        self.ready = False

    def validate(self, request):
        pass

    def submit(self, request):
        self.submitted += 1
        return "task-7"

    def observe(self, request, task_id):
        if self.ready:
            return {"status": "success", "vm_uuid": "uuid", "ip": "192.0.2.2"}
        return {"status": "pending"}


def test_concurrent_jobs_submit_once_and_recover(tmp_path):
    center = FakeCenter()
    db = tmp_path
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: job.execute(REQUEST, center, db, timeout=0), range(8)))
    assert {row["status"] for row in results} == {"pending"}
    assert center.submitted == 1
    center.ready = True
    assert job.execute(REQUEST, center, db, timeout=0)["status"] == "success"
    assert center.submitted == 1
    with pytest.raises(ValueError):
        job.execute(dict(REQUEST, cpu=4), center, db, timeout=0)


def test_lost_submit_receipt_never_clones_again(tmp_path):
    class LostReceipt(FakeCenter):
        def submit(self, request):
            self.submitted += 1
            raise TimeoutError()

    center = LostReceipt()
    db = tmp_path
    with pytest.raises(TimeoutError):
        job.execute(REQUEST, center, db, timeout=0)
    assert job.execute(REQUEST, center, db, timeout=0)["status"] == "pending"
    assert center.submitted == 1


@pytest.mark.parametrize(
    "change", [{"profile": "../secret"}, {"cpu": True}, {"data_disk_gib": -2}, {"delivery_id": "a; echo"}, {"password": "secret"}]
)
def test_decode_rejects_unsafe_input(change):
    raw = base64.urlsafe_b64encode(json.dumps(dict(REQUEST, **change)).encode()).decode()
    with pytest.raises(ValueError):
        job.decode(raw)


def test_clone_spec_uses_selected_datastore_network_size_and_hostname():
    from types import SimpleNamespace

    vim = pytest.importorskip("pyVmomi").vim
    profile = json.loads((SCRIPT.parent / "profile.example.json").read_text())
    custom = vim.vm.customization.Specification(
        identity=vim.vm.customization.LinuxPrep(),
        nicSettingMap=[vim.vm.customization.AdapterMapping(adapter=vim.vm.customization.IPSettings(ip=vim.vm.customization.DhcpIpGenerator()))],
    )
    manager = SimpleNamespace(GetCustomizationSpec=lambda name: SimpleNamespace(spec=custom))
    service = SimpleNamespace(_stub=None, content=SimpleNamespace(customizationSpecManager=manager))
    center = job.VCenter(service, profile)
    devices = [
        vim.vm.device.VirtualVmxnet3(key=4000),
        vim.vm.device.VirtualLsiLogicSASController(key=1000, scsiCtlrUnitNumber=7),
        vim.vm.device.VirtualDisk(key=2000, controllerKey=1000, unitNumber=0),
    ]
    center.template = SimpleNamespace(config=SimpleNamespace(hardware=SimpleNamespace(device=devices)))
    center.store = vim.Datastore("datastore-8", None)

    # 使用真实 SDK 对象构造参数，网络命名通过 StubAdapter 伪造只读属性。
    class Stub:
        def InvokeAccessor(self, mo, info):
            return "network-a"

    center.network = vim.Network("network-8", Stub())
    spec = center.build_spec(REQUEST)
    assert spec.powerOn and spec.location.datastore._moId == "datastore-8"
    assert spec.location.pool._moId == profile["resource_pool_id"]
    assert spec.config.numCPUs == 2 and spec.config.memoryMB == 4096
    nic_change, disk_change = spec.config.deviceChange
    assert nic_change.device.backing.network._moId == "network-8"
    assert disk_change.device.capacityInKB == 20 * 1024**2
    assert disk_change.device.unitNumber == 1
    assert spec.customization.identity.hostName.name == center.identity(REQUEST)[0]


def test_query_failure_preserves_vcenter_task_receipt(tmp_path):
    class Offline(FakeCenter):
        def observe(self, request, task_id):
            raise TimeoutError()

    center = Offline()
    result = job.execute(REQUEST, center, tmp_path, timeout=0)
    assert result == {"status": "unconfirmed", "error_type": "TimeoutError", "delivery_id": "REQ42-1", "task_id": "task-7"}
    assert center.submitted == 1


def test_process_exit_after_send_preserves_private_receipt(tmp_path):
    import subprocess
    import sys

    program = """
import importlib.util, json, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('provision', sys.argv[1])
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)
class Interrupted:
    def validate(self, req): pass
    def submit(self, req): os._exit(73)
job.execute(json.loads(sys.argv[2]), Interrupted(), Path(sys.argv[3]), 0)
"""
    proc = subprocess.run([sys.executable, "-c", program, str(SCRIPT), json.dumps(REQUEST), str(tmp_path)])
    assert proc.returncode == 73
    receipt = next(tmp_path.glob("*.json"))
    assert receipt.stat().st_mode & 0o077 == 0
    assert json.loads(receipt.read_text())["task_id"] is None
    center = FakeCenter()
    assert job.execute(REQUEST, center, tmp_path, 0)["status"] == "pending"
    assert center.submitted == 0


@pytest.mark.parametrize(
    ("task_state", "guest_host", "address", "expected"),
    [
        ("running", "delivered", "192.0.2.20", "pending"),
        ("error", "delivered", "192.0.2.20", "failed"),
        ("success", "template-host", "192.0.2.20", "pending"),
        ("success", "delivered", "169.254.1.2", "pending"),
        ("success", "delivered", "192.0.2.20", "success"),
    ],
)
def test_observe_requires_completed_clone_and_customized_guest(task_state, guest_host, address, expected):
    from types import SimpleNamespace as NS

    vim = pytest.importorskip("pyVmomi").vim
    profile = json.loads((SCRIPT.parent / "profile.example.json").read_text())

    class Stub:
        def InvokeAccessor(self, mo, info):
            if isinstance(mo, vim.Task):
                return NS(state=task_state, error=Exception())
            name, marker = center.identity(REQUEST)
            return dict(
                config=NS(instanceUuid="uuid", annotation=marker),
                runtime=NS(powerState="poweredOn"),
                guest=NS(toolsRunningStatus="guestToolsRunning", hostName=name if guest_host == "delivered" else guest_host, ipAddress=address),
            )[info.name]

    stub = Stub()
    machine = vim.VirtualMachine("vm-43", stub)
    center = job.VCenter(NS(_stub=stub, content=NS(searchIndex=NS(FindChild=lambda **_: machine))), profile)
    actual = center.observe(REQUEST, "task-7")
    assert actual["status"] == expected
    if expected == "success":
        assert (actual["vm_id"], actual["vm_uuid"], actual["ip"]) == ("vm-43", "uuid", "192.0.2.20")


def test_readonly_check_never_submits_and_only_prints_delivery_id(tmp_path, monkeypatch, capsys):
    import sys
    from unittest.mock import Mock

    connect = pytest.importorskip("pyVim.connect")
    request = base64.urlsafe_b64encode(json.dumps(REQUEST).encode()).decode()
    monkeypatch.setattr(sys, "argv", ["job", "--check", request])
    password = tmp_path / "secret"
    password.write_text("simulation")
    password.chmod(0o600)
    profile = {"host": "vc.invalid", "username": "check", "password_file": str(password)}
    (tmp_path / "test.json").write_text(json.dumps(profile))
    monkeypatch.setenv("BKLITE_VMWARE_PROFILES", str(tmp_path))
    client = Mock()
    monkeypatch.setattr(connect, "SmartConnect", lambda **kw: object())
    disconnect = Mock()
    monkeypatch.setattr(connect, "Disconnect", disconnect)
    monkeypatch.setattr(job, "VCenter", lambda *args: client)
    assert job.main() == 0
    assert json.loads(capsys.readouterr().out) == {"status": "validated", "delivery_id": REQUEST["delivery_id"]}
    client.validate.assert_called_once_with(REQUEST)
    client.submit.assert_not_called()
    disconnect.assert_called_once()


def test_wrong_vcenter_is_rejected_before_connecting(tmp_path, monkeypatch):
    import sys
    from unittest.mock import Mock

    connect = pytest.importorskip("pyVim.connect")
    monkeypatch.setattr(sys, "argv", ["job", base64.urlsafe_b64encode(json.dumps(REQUEST).encode()).decode()])
    (tmp_path / "test.json").write_text(json.dumps({"host": "another.invalid"}))
    monkeypatch.setenv("BKLITE_VMWARE_PROFILES", str(tmp_path))
    client = Mock()
    monkeypatch.setattr(connect, "SmartConnect", client)
    with pytest.raises(ValueError, match="vCenter"):
        job.main()
    client.assert_not_called()
