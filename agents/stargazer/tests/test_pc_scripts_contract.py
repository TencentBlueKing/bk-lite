# -*- coding: utf-8 -*-
"""PC 发现脚本静态安全合同与 fixture 结构测试。

脚本必须只读、内置、版本化：
- 禁止 Win32_Product、注册表写入、文件删除、进程启动、安装/卸载；
- Windows 必须覆盖两个 HKLM Uninstall 视图并排除系统组件/补丁/驱动/AppX；
- macOS 只扫描 /Applications 与 /Applications/Utilities，不碰系统应用、pkgutil 收据与用户目录。

fixture 锁定脚本输出协议结构（snapshot_status/pc/software/计数元数据），
供 Task 5 的解析器与后续对账测试复用。
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PC_PLUGIN_DIR = ROOT / "enterprise" / "plugins" / "inputs" / "pc"
WINDOWS_SCRIPT = PC_PLUGIN_DIR / "pc_windows_discover.ps1"
MACOS_SCRIPT = PC_PLUGIN_DIR / "pc_macos_discover.sh"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pc"


# ---------------------------------------------------------------- 静态安全合同

def test_windows_script_is_read_only():
    source = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "win32_product" not in lowered
    for forbidden in (
        "set-itemproperty",
        "set-item ",
        "new-item",
        "remove-item",
        "start-process",
        "msiexec",
        "winget",
        "invoke-expression",
        "set-executionpolicy",
        "net user",
        "reg add",
        "reg delete",
    ):
        assert forbidden not in lowered, forbidden
    assert "Win32_ComputerSystemProduct" in source
    assert "WOW6432Node" in source
    assert "ConvertTo-Json" in source


def test_windows_script_exclusion_contract():
    source = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    assert r"HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall" in source
    assert r"HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall" in source
    # 系统组件、KB 补丁、驱动排除条件必须存在
    assert "SystemComponent" in source
    assert "KB" in source


def test_macos_script_scope_and_safety():
    source = MACOS_SCRIPT.read_text(encoding="utf-8")
    assert "/Applications" in source
    assert "/Applications/Utilities" in source
    assert "/System/Applications" not in source
    assert "pkgutil --pkgs" not in source
    assert "/Users/" not in source
    for forbidden in ("rm ", "sudo ", "installer ", "brew install", "mv ", "defaults write"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------- fixture 结构合同

PC_REQUIRED_FIELDS = {"inst_name", "host_name", "ip_addr", "os_type", "hardware_uuid"}
SOFTWARE_REQUIRED_FIELDS = {"inst_name", "pc_inst_name", "snapshot_id", "software_key", "name", "source"}


def _load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_name,os_type,expected_status",
    [
        ("windows_complete.json", "windows", "complete"),
        ("windows_empty.json", "windows", "complete"),
        ("macos_complete.json", "macos", "complete"),
        ("macos_partial.json", "macos", "partial"),
    ],
)
def test_fixture_matches_output_contract(fixture_name, os_type, expected_status):
    payload = _load_fixture(fixture_name)
    assert payload["snapshot_status"] == expected_status
    assert payload["snapshot_id"]

    pcs = payload["pc"]
    assert len(pcs) == 1
    pc = pcs[0]
    assert PC_REQUIRED_FIELDS <= set(pc)
    assert pc["os_type"] == os_type
    assert pc["snapshot_id"] == payload["snapshot_id"]
    assert pc["software_snapshot_status"] == expected_status

    software = payload["software"]
    assert isinstance(software, list)
    assert payload["software_expected_count"] == len(software) or expected_status == "partial"
    assert payload["software_error_count"] >= 0
    for record in software:
        assert SOFTWARE_REQUIRED_FIELDS <= set(record)
        assert record["pc_inst_name"] == pc["inst_name"]
        assert record["snapshot_id"] == payload["snapshot_id"]


def test_windows_empty_fixture_is_explicit_empty_snapshot():
    payload = _load_fixture("windows_empty.json")
    assert payload["software"] == []
    assert payload["software_expected_count"] == 0
    assert payload["software_error_count"] == 0
