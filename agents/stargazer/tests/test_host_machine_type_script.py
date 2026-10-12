# -*- coding: utf-8 -*-
"""主机采集脚本的机器类型判断。脚本单文件下发，函数留在发现脚本里。"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

LINUX_SCRIPT = Path(__file__).resolve().parents[1] / "plugins/inputs/host/host_default_discover.sh"
WINDOWS_SCRIPT = Path(__file__).resolve().parents[1] / "plugins/inputs/host/host_windows_discover.ps1"


def _classify_linux(virt_type, vendor, product, cpuinfo):
    completed = subprocess.run(
        [
            "sh",
            "-c",
            '. "$1" && classify_host_machine_type "$2" "$3" "$4" "$5"',
            "sh",
            str(LINUX_SCRIPT),
            virt_type,
            vendor,
            product,
            cpuinfo,
        ],
        env={**os.environ, "HOST_DISCOVER_SOURCE_ONLY": "1"},
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


@pytest.mark.parametrize(
    "virt,vendor,product,cpuinfo,expected",
    [
        ("kvm", "", "", "", "virtual"),
        ("docker", "Dell Inc.", "PowerEdge R740", "", "virtual"),
        ("none", "VMware, Inc.", "VMware Virtual Platform", "", "virtual"),
        ("none", "Dell Inc.", "PowerEdge R740", "fpu vme", "physical_server"),
        ("", "Huawei", "2288H V5", "", "physical_server"),
        ("", "", "", "fpu hypervisor vme", "virtual"),
        ("", "", "", "", "unknown"),
        ("none", "Microsoft Corporation", "Surface", "", "physical_server"),
    ],
)
def test_linux_classify_host_machine_type(virt, vendor, product, cpuinfo, expected):
    assert _classify_linux(virt, vendor, product, cpuinfo) == expected


def test_linux_discover_script_emits_machine_type():
    text = LINUX_SCRIPT.read_text(encoding="utf-8")
    assert "classify_host_machine_type" in text
    assert '"machine_type"' in text


def test_windows_discover_script_emits_machine_type():
    text = WINDOWS_SCRIPT.read_text(encoding="utf-8")
    assert "Get-HostMachineType" in text
    assert "machine_type" in text


def _powershell():
    return shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(_powershell() is None, reason="本机没有 PowerShell")
@pytest.mark.parametrize(
    "present,manufacturer,model,expected",
    [
        ("$true", "VMware, Inc.", "VMware Virtual Platform", "virtual"),
        ("$false", "Microsoft Corporation", "PowerEdge R740", "physical_server"),
        ("$true", "Dell Inc.", "PowerEdge R740", "virtual"),
        ("$null", "", "", "unknown"),
    ],
)
def test_windows_get_host_machine_type(present, manufacturer, model, expected):
    script = f"""
    $env:HOST_DISCOVER_SOURCE_ONLY = '1'
    . '{WINDOWS_SCRIPT}'
    Get-HostMachineType -HypervisorPresent {present} -Manufacturer '{manufacturer}' -Model '{model}'
    """
    completed = subprocess.run(
        [_powershell(), "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip().splitlines()[-1] == expected
