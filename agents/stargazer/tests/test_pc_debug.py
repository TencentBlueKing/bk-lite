# -*- coding: utf-8 -*-
"""PC 最小连接测试（连接测试专用身份链路）合同测试。

锁定：
- Windows 只执行 CIM 身份命令（Win32_ComputerSystemProduct/Win32_BIOS 等），
  不执行 Win32_Product、注册表 Uninstall 扫描或任何 CMDB callback；
- macOS 只执行 ioreg/sw_vers 身份命令，不扫描 /Applications；
- 连接测试脚本级超时固定 15 秒；
- 成功返回 {success, os_type, inst_name, hardware_uuid, serial_number}；
- 失败只返回稳定错误码（PC_ERROR_CODES 内），不泄露内部细节；
- 复用 PCInventoryCollector 的连接构造与身份规范化，但使用固定最小身份脚本。
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from enterprise.plugins.inputs.pc.pc_inventory import PC_ERROR_CODES  # noqa: E402
from service.debug.pc_debug import (  # noqa: E402
    PC_CONNECTION_TEST_TIMEOUT,
    run_pc_test_connection,
)

IDENTITY_SCRIPT_DIR = ROOT / "enterprise" / "plugins" / "inputs" / "pc"

WIN_UUID = "4C4C4544-0038-5810-805A-CAC04F595832"
MAC_UUID = "A1B2C3D4-1234-4F5E-8A9B-0C1D2E3F4A5B"


def _windows_params(**overrides):
    params = {
        "os_type": "windows",
        "host": "10.0.0.8",
        "node_id": "node-1",
        "username": "ACME\\alice",
        "password": "secret",
        "port": 5986,
        "winrm_scheme": "https",
        "winrm_transport": "ntlm",
        "winrm_cert_validation": False,
    }
    params.update(overrides)
    return params


def _macos_params(**overrides):
    params = {
        "os_type": "macos",
        "host": "10.0.0.9",
        "node_id": "node-1",
        "username": "admin",
        "password": "secret",
        "port": 22,
    }
    params.update(overrides)
    return params


def _identity_payload(os_type, inst_name, hardware_uuid, serial_number):
    return {
        "snapshot_status": "complete",
        "snapshot_id": "snapshot-test-1",
        "pc": [
            {
                "inst_name": inst_name,
                "os_type": os_type,
                "hardware_uuid": hardware_uuid,
                "serial_number": serial_number,
                "host_name": "DESKTOP-1",
                "os_name": "Windows 11 Pro",
            }
        ],
        "software": [],
        "software_expected_count": 0,
        "software_error_count": 0,
    }


@pytest.mark.asyncio
async def test_windows_connection_test_runs_only_cim_identity_commands(monkeypatch):
    captured = {}

    async def fake_adhoc(**kwargs):
        captured.update(kwargs)
        payload = _identity_payload("windows", f"WIN-{WIN_UUID}", WIN_UUID, "")
        return {"success": True, "result": [{"stdout": json.dumps(payload)}]}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is True
    assert result["os_type"] == "windows"
    assert result["inst_name"] == f"WIN-{WIN_UUID}"
    assert result["hardware_uuid"] == WIN_UUID
    # 连接测试脚本级超时固定 15 秒
    assert captured["execute_timeout"] == PC_CONNECTION_TEST_TIMEOUT == 15
    assert captured["module"] == "win_shell"
    script = captured["module_args"]
    # 只允许 CIM 身份命令
    assert "Win32_ComputerSystemProduct" in script
    assert "Win32_BIOS" in script
    # 禁止软件扫描与任何回传
    assert "Win32_Product" not in script
    assert "Uninstall" not in script
    assert "HKLM" not in script
    assert "Invoke-RestMethod" not in script
    assert "Invoke-WebRequest" not in script


@pytest.mark.asyncio
async def test_macos_connection_test_uses_identity_script_without_applications_scan(monkeypatch):
    captured = {}

    class FakeSSHPlugin:
        def __init__(self, params):
            captured.update(params)

        async def list_all_resources(self, need_raw=False):
            payload = _identity_payload("macos", f"MAC-{MAC_UUID}", MAC_UUID, "")
            return {"success": True, "result": json.dumps(payload)}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.SSHPlugin", FakeSSHPlugin
    )

    result = await run_pc_test_connection(_macos_params())

    assert result["success"] is True
    assert result["os_type"] == "macos"
    assert result["inst_name"] == f"MAC-{MAC_UUID}"
    # 走固定最小身份脚本，而非完整发现脚本
    assert captured["script_path"].endswith("pc_macos_identity.sh")
    assert captured["execute_timeout"] == PC_CONNECTION_TEST_TIMEOUT


@pytest.mark.asyncio
async def test_identity_scripts_are_read_only_and_minimal():
    """直接锁定随插件发布的最小身份脚本内容：只读身份命令、无软件扫描、无回传。"""
    windows_script = (IDENTITY_SCRIPT_DIR / "pc_windows_identity.ps1").read_text(encoding="utf-8")
    assert "Win32_ComputerSystemProduct" in windows_script
    assert "Win32_Product" not in windows_script
    assert "Uninstall" not in windows_script
    assert "Invoke-RestMethod" not in windows_script
    assert "callback" not in windows_script.lower()

    macos_script = (IDENTITY_SCRIPT_DIR / "pc_macos_identity.sh").read_text(encoding="utf-8")
    assert "ioreg" in macos_script
    assert "/Applications" not in macos_script
    assert "callback" not in macos_script.lower()
    # 完整发现脚本才允许扫描 /Applications
    discover_script = (IDENTITY_SCRIPT_DIR / "pc_macos_discover.sh").read_text(encoding="utf-8")
    assert "/Applications" in discover_script


@pytest.mark.asyncio
async def test_windows_auth_failure_maps_to_stable_error_code(monkeypatch):
    async def fake_adhoc(**kwargs):
        return {"success": False, "result": [{"msg": "winrm auth unauthorized 401"}]}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is False
    assert result["error_code"] == "WINRM_AUTH_FAILED"
    assert result["error_code"] in PC_ERROR_CODES
    assert "secret" not in json.dumps(result)


@pytest.mark.asyncio
async def test_unreachable_target_maps_to_stable_error_code(monkeypatch):
    async def fake_adhoc(**kwargs):
        return {"success": False, "result": [{"unreachable": True, "msg": "timed out"}]}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is False
    assert result["error_code"] == "TARGET_UNREACHABLE"


@pytest.mark.asyncio
async def test_invalid_identity_maps_to_stable_error_code(monkeypatch):
    async def fake_adhoc(**kwargs):
        payload = _identity_payload("windows", "", "", "")
        payload["snapshot_status"] = "failed"
        payload["error_code"] = "PC_IDENTITY_INVALID"
        payload["pc"] = []
        return {"success": True, "result": [{"stdout": json.dumps(payload)}]}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is False
    assert result["error_code"] == "PC_IDENTITY_INVALID"


@pytest.mark.asyncio
async def test_unsupported_os_type_rejected_without_executor_call(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", spy
    )

    result = await run_pc_test_connection(_windows_params(os_type="linux"))

    assert result["success"] is False
    assert result["error_code"] in PC_ERROR_CODES
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_script_timeout_maps_to_stable_error_code(monkeypatch):
    async def fake_adhoc(**kwargs):
        raise TimeoutError()

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is False
    assert result["error_code"] == "SCRIPT_TIMEOUT"


@pytest.mark.asyncio
async def test_unknown_script_error_code_sanitized(monkeypatch):
    """脚本自报的非合同错误码不得透传，统一兜底为稳定错误码。"""

    async def fake_adhoc(**kwargs):
        payload = _identity_payload("windows", "", "", "")
        payload["snapshot_status"] = "failed"
        payload["error_code"] = "SOME_RANDOM_TEXT_WITH_secret"
        payload["pc"] = []
        return {"success": True, "result": [{"stdout": json.dumps(payload)}]}

    monkeypatch.setattr(
        "enterprise.plugins.inputs.pc.pc_inventory.ansible_adhoc", fake_adhoc
    )

    result = await run_pc_test_connection(_windows_params())

    assert result["success"] is False
    assert result["error_code"] in PC_ERROR_CODES
    assert "SOME_RANDOM_TEXT" not in json.dumps(result)
    assert "secret" not in json.dumps(result)
