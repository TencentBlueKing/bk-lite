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
    assert '"mounts"' in text
    assert '"nics"' in text


def _script_function(name, stdin_text):
    completed = subprocess.run(
        [
            "sh",
            "-c",
            f'. "$1" && {name}',
            "sh",
            str(LINUX_SCRIPT),
        ],
        input=stdin_text,
        env={**os.environ, "HOST_DISCOVER_SOURCE_ONLY": "1"},
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_json_from_df_keeps_real_mounts():
    raw = """Filesystem Type 1024-blocks Used Available Capacity Mounted
/dev/sda1 ext4 41943040 1 1 1% /
tmpfs tmpfs 102400 1 1 1% /run
/dev/sdb1 xfs 104857600 1 1 1% /data
"""
    import json

    rows = json.loads(_script_function("json_from_df", raw))
    assert rows == [
        {"device": "/dev/sda1", "mount": "/", "fstype": "ext4", "size_gb": "40.0"},
        {"device": "/dev/sdb1", "mount": "/data", "fstype": "xfs", "size_gb": "100.0"},
    ]


def test_json_from_df_joins_wrapped_device_name():
    raw = """Filesystem Type 1024-blocks Used Available Capacity Mounted
/dev/mapper/vg-very-long
xfs 104857600 1 1 1% /data
"""
    import json

    rows = json.loads(_script_function("json_from_df", raw))
    assert rows == [{"device": "/dev/mapper/vg-very-long", "mount": "/data", "fstype": "xfs", "size_gb": "100.0"}]


def test_json_from_nic_rows_skips_loopback_and_joins_ips():
    raw = """LINK lo 00:00:00:00:00:00
LINK eth0 aa:bb:cc:dd:ee:ff
ADDR lo 127.0.0.1/8
ADDR eth0 10.0.0.8/24
ADDR eth0 10.0.0.9/24
"""
    import json

    rows = json.loads(_script_function("json_from_nic_rows", raw))
    assert rows == [{"name": "eth0", "mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.8,10.0.0.9"}]


def test_json_from_nic_rows_skips_virtual_interfaces():
    raw = """LINK veth1234 aa:bb:cc:dd:ee:01
LINK docker0 aa:bb:cc:dd:ee:02
LINK ens192 aa:bb:cc:dd:ee:03
ADDR veth1234 172.17.0.2/16
ADDR ens192 10.1.1.8/24
"""
    import json

    rows = json.loads(_script_function("json_from_nic_rows", raw))
    assert rows == [{"name": "ens192", "mac": "aa:bb:cc:dd:ee:03", "ip": "10.1.1.8"}]


def test_stable_pids_drops_processes_seen_once():
    raw = """1 nginx
2 curl
---
1 nginx
3 bash
---
1 nginx
3 bash
4 ls
"""
    got = _script_function("stable_pids", raw)
    assert sorted(got.split()) == ["1", "3"]


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
