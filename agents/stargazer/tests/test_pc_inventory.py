# -*- coding: utf-8 -*-
"""PCInventoryCollector 路由、身份规范化与资源边界测试。

锁定：
- Windows 固定路由到 ansible_adhoc(win_shell + winrm)；macOS 固定路由到既有 SSHPlugin；
- PC 身份规范化（UUID 优先、占位回退序列号、双无效失败）；
- 软件实例名稳定且与版本无关；
- 输出边界（10MB / 5000 条 / 1024 字符）降级且不可删除；
- 执行异常映射到稳定错误码；
- 非法 OS/协议组合拒绝。
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pc"


def _load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


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
        "execute_timeout": 120,
        "script_path": "enterprise/plugins/inputs/pc/pc_windows_discover.ps1",
        "model_id": "pc",
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
        "execute_timeout": 120,
        "script_path": "enterprise/plugins/inputs/pc/pc_macos_discover.sh",
        "model_id": "pc",
    }
    params.update(overrides)
    return params


@pytest.fixture()
def pc_inventory():
    from enterprise.plugins.inputs.pc import pc_inventory as module

    return module


def test_script_path_is_limited_to_builtin_pc_scripts(pc_inventory):
    collector = pc_inventory.PCInventoryCollector(_windows_params(script_path="../../../../etc/passwd"))

    with pytest.raises(pc_inventory.PCInventoryError, match="SCRIPT_OUTPUT_INVALID"):
        collector._read_script()


@pytest.mark.asyncio
async def test_macos_rejects_non_builtin_script_before_ssh_execution(
    pc_inventory,
    monkeypatch,
):
    ssh_plugin = Mock()
    monkeypatch.setattr(pc_inventory, "SSHPlugin", ssh_plugin)

    result = await pc_inventory.PCInventoryCollector(_macos_params(script_path="/etc/passwd")).list_all_resources()

    assert result["success"] is False
    assert result["result"]["cmdb_collect_error"].startswith("SCRIPT_OUTPUT_INVALID")
    ssh_plugin.assert_not_called()


# ---------------------------------------------------------------- 路由


@pytest.mark.asyncio
async def test_windows_routes_to_winrm(pc_inventory, monkeypatch):
    payload = _load_fixture("windows_complete.json")
    mock_ansible = AsyncMock(return_value={"success": True, "result": [{"host": "10.0.0.8", "stdout": json.dumps(payload)}]})
    monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)

    result = await pc_inventory.PCInventoryCollector(_windows_params()).list_all_resources()

    kwargs = mock_ansible.await_args.kwargs
    assert kwargs["module"] == "win_shell"
    assert kwargs["host_credentials"][0]["connection"] == "winrm"
    assert kwargs["host_credentials"][0]["port"] == 5986
    assert kwargs["host_credentials"][0]["winrm_scheme"] == "https"
    assert kwargs["host_credentials"][0]["winrm_transport"] == "ntlm"
    assert result["success"] is True
    pc_row = result["result"]["pc"][0]
    assert pc_row["inst_name"].startswith("WIN-")
    assert pc_row["ip_addr"] == "10.0.0.8"
    sw_row = result["result"]["pc_software"][0]
    assert sw_row["inst_name"].startswith("SW-")
    assert sw_row["pc_inst_name"] == pc_row["inst_name"]
    assert "snapshot_id" not in sw_row
    assert "snapshot_id" not in pc_row
    assert result["snapshot_id"]


@pytest.mark.asyncio
async def test_macos_routes_to_existing_ssh(pc_inventory, monkeypatch):
    payload = _load_fixture("macos_complete.json")

    class _FakeSSH:
        def __init__(self, params):
            self.params = params

        async def list_all_resources(self, need_raw=False):
            return {"success": True, "result": json.dumps(payload)}

    monkeypatch.setattr(pc_inventory, "SSHPlugin", _FakeSSH)

    result = await pc_inventory.PCInventoryCollector(_macos_params()).list_all_resources()

    assert result["success"] is True
    assert result["result"]["pc"][0]["inst_name"].startswith("MAC-")
    assert result["result"]["pc_software"][0]["inst_name"].startswith("SW-")


@pytest.mark.asyncio
async def test_unknown_os_type_rejected(pc_inventory):
    result = await pc_inventory.PCInventoryCollector(_windows_params(os_type="linux")).list_all_resources()
    assert result["success"] is False


# ---------------------------------------------------------------- 身份规范化


def test_build_pc_inst_name_uuid_priority(pc_inventory):
    assert pc_inventory.build_pc_inst_name("windows", "4c4c4544-0038-5910-8058-c4c04f433632", "") == "WIN-4C4C4544-0038-5910-8058-C4C04F433632"
    assert pc_inventory.build_pc_inst_name("macos", "{00001111-2222-3333-4444-555566667777}", "") == "MAC-00001111-2222-3333-4444-555566667777"


@pytest.mark.parametrize(
    "bad_uuid",
    [
        "",
        "00000000-0000-0000-0000-000000000000",
        "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
        "4C4C4544-00385-910-8058-C4C04F433632",
        "To Be Filled By O.E.M.",
    ],
)
def test_build_pc_inst_name_falls_back_to_serial(pc_inventory, bad_uuid):
    assert pc_inventory.build_pc_inst_name("windows", bad_uuid, "sn-abc 123") == "WIN-SN-SN-ABC 123"


def test_build_pc_inst_name_both_invalid(pc_inventory):
    with pytest.raises(pc_inventory.PCInventoryError) as exc:
        pc_inventory.build_pc_inst_name("windows", "", "")
    assert "PC_IDENTITY_INVALID" in str(exc.value)


def test_software_inst_name_stable_and_version_free(pc_inventory):
    name_v1 = pc_inventory.build_software_inst_name("WIN-AAA", "google chrome|google llc")
    name_v2 = pc_inventory.build_software_inst_name("WIN-AAA", "google chrome|google llc")
    assert name_v1 == name_v2
    assert name_v1.startswith("SW-")
    assert len(name_v1) == 3 + 32
    other_pc = pc_inventory.build_software_inst_name("WIN-BBB", "google chrome|google llc")
    assert other_pc != name_v1


# ---------------------------------------------------------------- 快照规范化与边界


def test_normalization_marks_complete_snapshot(pc_inventory):
    payload = _load_fixture("windows_complete.json")
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.8")
    assert normalized["success"] is True
    pc_row = normalized["result"]["pc"][0]
    assert normalized["snapshot_status"] == "complete"
    assert normalized["snapshot_metadata"] == {
        "software_expected_count": 1,
        "software_error_count": 0,
    }
    assert "snapshot_id" not in pc_row


def test_partial_snapshot_never_deletable(pc_inventory):
    payload = _load_fixture("macos_partial.json")
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.9")
    assert normalized["snapshot_status"] == "partial"
    assert normalized["snapshot_metadata"]["software_error_count"] == 2


def test_oversize_field_degrades_snapshot(pc_inventory):
    payload = _load_fixture("windows_complete.json")
    payload["software"][0]["name"] = "x" * 2000
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.8")
    assert normalized["snapshot_status"] == "partial"
    assert len(normalized["result"]["pc_software"][0]["name"]) <= 1024


def test_software_overflow_degrades_snapshot(pc_inventory):
    payload = _load_fixture("windows_complete.json")
    template = payload["software"][0]
    payload["software"] = [dict(template, name=f"app-{i}") for i in range(5001)]
    payload["software_expected_count"] = 5001
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.8")
    assert normalized["snapshot_status"] == "partial"
    assert len(normalized["result"]["pc_software"]) <= 5000


def test_failed_snapshot_returns_error(pc_inventory):
    payload = {
        "snapshot_status": "failed",
        "snapshot_id": "x",
        "pc": [],
        "software": [],
        "software_expected_count": 0,
        "software_error_count": 0,
        "error_code": "PC_IDENTITY_INVALID",
    }
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.8")
    assert normalized["success"] is False
    assert "PC_IDENTITY_INVALID" in json.dumps(normalized, ensure_ascii=False)


def test_empty_complete_snapshot_kept(pc_inventory):
    payload = _load_fixture("windows_empty.json")
    normalized = pc_inventory.normalize_snapshot(payload, host="10.0.0.8")
    assert normalized["success"] is True
    assert normalized["snapshot_status"] == "complete"
    assert normalized["snapshot_metadata"]["software_expected_count"] == 0
    assert normalized["result"]["pc_software"] == []


# ---------------------------------------------------------------- 错误映射


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "side_effect,expected_code",
    [
        (TimeoutError("nats timeout"), "SCRIPT_TIMEOUT"),
        (RuntimeError("No ansible executor subscribed for node"), "TARGET_UNREACHABLE"),
    ],
)
async def test_windows_exception_mapped_to_error_code(pc_inventory, monkeypatch, side_effect, expected_code):
    mock_ansible = AsyncMock(side_effect=side_effect)
    monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)
    result = await pc_inventory.PCInventoryCollector(_windows_params()).list_all_resources()
    assert result["success"] is False
    assert expected_code in json.dumps(result, ensure_ascii=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ansible_result,expected_code",
    [
        ({"success": False, "result": [{"host": "10.0.0.8", "unreachable": True, "msg": "timed out"}]}, "TARGET_UNREACHABLE"),
        ({"success": False, "result": [{"host": "10.0.0.8", "failed": True, "msg": "winrm unauthorized 401"}]}, "WINRM_AUTH_FAILED"),
        ({"success": False, "result": [{"host": "10.0.0.8", "failed": True, "msg": "SSL certificate verify failed"}]}, "WINRM_TLS_FAILED"),
    ],
)
async def test_windows_structured_failure_mapped(pc_inventory, monkeypatch, ansible_result, expected_code):
    mock_ansible = AsyncMock(return_value=ansible_result)
    monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)
    result = await pc_inventory.PCInventoryCollector(_windows_params()).list_all_resources()
    assert result["success"] is False
    assert expected_code in json.dumps(result, ensure_ascii=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ssh_error,expected_code",
    [
        ("Authentication failed", "SSH_AUTH_FAILED"),
        ("private key invalid or passphrase mismatch", "SSH_KEY_INVALID"),
    ],
)
async def test_macos_ssh_failure_mapped(pc_inventory, monkeypatch, ssh_error, expected_code):
    class _FakeSSH:
        def __init__(self, params):
            pass

        async def list_all_resources(self, need_raw=False):
            return {"success": False, "result": {"cmdb_collect_error": ssh_error}}

    monkeypatch.setattr(pc_inventory, "SSHPlugin", _FakeSSH)
    result = await pc_inventory.PCInventoryCollector(_macos_params()).list_all_resources()
    assert result["success"] is False
    assert expected_code in json.dumps(result, ensure_ascii=False)


@pytest.mark.asyncio
async def test_invalid_script_output_mapped(pc_inventory, monkeypatch):
    mock_ansible = AsyncMock(return_value={"success": True, "result": [{"host": "10.0.0.8", "stdout": "not-a-json"}]})
    monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)
    result = await pc_inventory.PCInventoryCollector(_windows_params()).list_all_resources()
    assert result["success"] is False
    assert "SCRIPT_OUTPUT_INVALID" in json.dumps(result, ensure_ascii=False)
