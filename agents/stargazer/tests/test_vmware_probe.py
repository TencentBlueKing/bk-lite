"""VMware CredentialAttempt（配置 + monitor）契约测试。"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from core.collection.contracts import AccessProbeResult, AccessProbeStatus


def _install_pyvmomi_stubs(monkeypatch):
    pyvim = types.ModuleType("pyVim")
    connect = types.ModuleType("pyVim.connect")
    connect.Disconnect = MagicMock()
    connect.SmartConnect = MagicMock()
    pyvim.connect = connect
    pyvmomi = types.ModuleType("pyVmomi")
    pyvmomi.vim = MagicMock()
    monkeypatch.setitem(sys.modules, "pyVim", pyvim)
    monkeypatch.setitem(sys.modules, "pyVim.connect", connect)
    monkeypatch.setitem(sys.modules, "pyVmomi", pyvmomi)


@pytest.fixture
def vmware_modules(monkeypatch):
    _install_pyvmomi_stubs(monkeypatch)
    sys.modules.pop("plugins.inputs.vmware_vc.vmware_info", None)
    sys.modules.pop("tasks.collectors.vmware_collector", None)
    from plugins.inputs.vmware_vc.vmware_info import VmwareManage
    from tasks.collectors.vmware_collector import VmwareCollector

    return VmwareManage, VmwareCollector


@pytest.mark.asyncio
async def test_vmware_manage_probe_ready_on_connect_success(vmware_modules):
    VmwareManage, _VmwareCollector = vmware_modules
    manager = VmwareManage(
        {
            "username": "admin",
            "password": "secret",
            "hostname": "vcenter.example",
        }
    )

    with patch.object(manager, "connect_vc"), patch.object(
        manager, "disconnect_vc"
    ) as disconnect:
        result = await manager.probe()

    assert result.status == AccessProbeStatus.READY
    disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_vmware_manage_probe_maps_auth_failure(vmware_modules):
    VmwareManage, _VmwareCollector = vmware_modules
    manager = VmwareManage(
        {
            "username": "admin",
            "password": "bad",
            "hostname": "vcenter.example",
        }
    )

    def boom():
        raise RuntimeError(
            "Connect vcenter error! incorrect user name or password"
        )

    with patch.object(manager, "connect_vc", side_effect=boom), patch.object(
        manager, "disconnect_vc"
    ):
        result = await manager.probe()

    assert result.status == AccessProbeStatus.AUTH_FAILED
    assert result.error_code == "authentication_failed"


@pytest.mark.asyncio
async def test_vmware_collector_probe_reuses_manage_attempt(vmware_modules):
    VmwareManage, VmwareCollector = vmware_modules
    collector = VmwareCollector(
        {
            "username": "admin",
            "password": "secret",
            "host": "vcenter.example",
        }
    )

    with patch.object(
        VmwareManage,
        "_probe_sync",
        return_value=AccessProbeResult(status=AccessProbeStatus.READY),
    ):
        result = await collector.probe()

    assert result.status == AccessProbeStatus.READY


def _sample_object_map():
    return {
        "vmware_vc": [{"inst_name": "vc-prod"}],
        "vmware_esxi": [
            {
                "resource_id": "host-1",
                "ip_addr": "10.10.16.10",
                "inst_name": "esxi-1[host-1]",
            }
        ],
        "vmware_vm": [
            {
                "resource_id": "vm-1",
                "ip_addr": "192.168.1.20",
                "inst_name": "web-1[vm-1]",
            },
            {
                "resource_id": "vm-2",
                "ip_addr": "",
                "inst_name": "db-1[vm-2]",
            },
        ],
        "vmware_ds": [
            {"resource_id": "datastore-1", "inst_name": "ds1[datastore-1]"}
        ],
    }


def _monitor_data_for_object(**kwargs):
    obj = kwargs["context"]["resources"][0]["bk_obj_id"]
    payload = {
        "vmware_esxi": {
            "host-1": {"cpu_usage_average": [[1700000000000, 12.5]]}
        },
        "vmware_vm": {
            "vm-1": {"cpu_usage_average": [[1700000000000, 8.0]]},
            "vm-2": {"cpu_usage_average": [[1700000000000, 3.0]]},
        },
        "vmware_ds": {
            "datastore-1": {"disk_used_average": [[1700000000000, 50.0]]}
        },
    }
    data = payload.get(obj)
    if not data:
        return {"result": False, "message": "skip"}
    return {"result": True, "data": data}


def test_vmware_collector_puts_esxi_and_vm_ip_on_metrics(vmware_modules):
    VmwareManage, VmwareCollector = vmware_modules
    collector = VmwareCollector(
        {
            "username": "admin",
            "password": "secret",
            "host": "10.10.16.254",
            "minutes": 5,
        }
    )
    driver = MagicMock()
    driver.get_weops_monitor_data.side_effect = _monitor_data_for_object

    with patch("common.cmp.driver.CMPDriver", return_value=driver), patch.object(
        VmwareManage, "connect_vc"
    ), patch.object(VmwareManage, "service", return_value=_sample_object_map()):
        output = collector._collect_sync()

    assert (
        'cpu_usage_average{resource_id="host-1", resource_type="vmware_esxi", ip="10.10.16.10"} 12.5 1700000000000'
        in output
    )
    assert (
        'cpu_usage_average{resource_id="vm-1", resource_type="vmware_vm", ip="192.168.1.20"} 8.0 1700000000000'
        in output
    )
    assert (
        'cpu_usage_average{resource_id="vm-2", resource_type="vmware_vm"} 3.0 1700000000000'
        in output
    )
    assert "ip=" not in [
        line for line in output.splitlines() if "datastore-1" in line
    ][0]
