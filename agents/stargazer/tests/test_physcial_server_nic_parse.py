# -*- coding: utf-8 -*-
"""物理服务器 SSH 脚本输出：网卡解析（lo / 空 MAC 丢弃，MAC 规范化）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins.inputs.physcial_server.server_info_parse import normalize_nic_mac, parse_server_info  # noqa: E402

SAMPLE_OUTPUT = """
=== NIC info ===
nic_pci_addr=00:00.0
nic_type=Ethernet
nic_vendor=Vendor
nic_model=Loopback
nic_iface=lo
nic_mac=00:11:22:33:44:55
nic_pci_addr=7d:00.0
nic_type=Ethernet controller
nic_vendor=Huawei
nic_model=HNS
nic_iface=enp125s0f0
nic_mac=B0-4F-A6-2C-B7-60
nic_pci_addr=7d:00.1
nic_type=Ethernet controller
nic_vendor=Huawei
nic_model=HNS
nic_iface=enp125s0f1
nic_mac=N/A
nic_pci_addr=7d:00.2
nic_type=Ethernet controller
nic_vendor=Huawei
nic_model=HNS
nic_iface=enp125s0f2
nic_mac=b0:4f:a6:2c:b7:62
"""


def test_normalize_nic_mac_lowercase_colon():
    assert normalize_nic_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_nic_mac("N/A") == ""
    assert normalize_nic_mac("00:00:00:00:00:00") == ""


def test_parse_server_info_drops_lo_and_empty_mac_and_normalizes():
    parsed = parse_server_info(SAMPLE_OUTPUT)
    nics = parsed["nic"]
    assert [item["nic_iface"] for item in nics] == ["enp125s0f0", "enp125s0f2"]
    assert [item["nic_mac"] for item in nics] == [
        "b0:4f:a6:2c:b7:60",
        "b0:4f:a6:2c:b7:62",
    ]
    assert all(item["nic_iface"] != "lo" for item in nics)
    assert all(item["nic_mac"] not in ("", "N/A", "n/a") for item in nics)
