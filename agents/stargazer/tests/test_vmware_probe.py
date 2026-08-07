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
