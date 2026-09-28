# -*- coding: utf-8 -*-
"""Redfish 协议插件：子实例写入与 SSH 实例名规则对齐。"""

import pytest

from apps.cmdb.collection.plugins.community.protocol.physical_server import PhysicalServerProtocolCollectionPlugin

pytestmark = pytest.mark.unit


@pytest.fixture
def protocol_plugin(monkeypatch):
    monkeypatch.setattr(
        PhysicalServerProtocolCollectionPlugin,
        "model_id",
        property(lambda self: "physcial_server"),
    )
    return PhysicalServerProtocolCollectionPlugin("10.0.0.8", "cmdb_2", 2)


def test_redfish_p0_keeps_physical_server_collect_task(protocol_plugin):
    assert protocol_plugin.supported_model_id == "physcial_server"
    assert "storage_controller_info_gauge" in protocol_plugin.metric_names
    assert "psu_info_gauge" in protocol_plugin.metric_names
    assert "fan_info_gauge" not in protocol_plugin.metric_names
    assert "psu_input_watts" not in protocol_plugin.related_field_mappings["psu"]


def test_redfish_child_gauges_use_ssh_instance_names(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "serial_number": "SERVER-SN-8",
            "cpu_cores": "32",
            "cpu_threads": "64",
            "cpu_arch": "x86_64",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["memory_info_gauge"] = [
        {
            "model_id": "memory",
            "mem_locator": "DIMM_A1",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["disk_info_gauge"] = [
        {
            "model_id": "disk",
            "disk_name": "Disk.Bay.0",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["nic_info_gauge"] = [
        {
            "model_id": "nic",
            "nic_mac": "AA:BB:CC:DD:EE:FF",
            "nic_iface": "eth0",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["gpu_info_gauge"] = [
        {
            "model_id": "gpu",
            "gpu_name": "A100",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    server = protocol_plugin.result["physcial_server"][0]
    assert server["inst_name"] == "10.0.0.8"
    assert server["cpu_core"] == 32
    assert server["cpu_threads"] == 64
    assert server["cpu_arch"] == "x64"

    memory = protocol_plugin.result["memory"][0]
    assert memory["inst_name"] == "DIMM_A1-10.0.0.8"
    assert memory["assos"][0]["inst_name"] == "10.0.0.8"

    disk = protocol_plugin.result["disk"][0]
    assert disk["inst_name"] == "Disk.Bay.0-10.0.0.8"

    nic = protocol_plugin.result["nic"][0]
    assert nic["inst_name"] == "aa:bb:cc:dd:ee:ff"

    gpu = protocol_plugin.result["gpu"][0]
    assert gpu["inst_name"] == "A100-10.0.0.8"


def test_parent_only_format_metrics_includes_inst_name(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "serial_number": "SERVER-SN-8",
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    assert protocol_plugin.result["physcial_server"][0]["inst_name"] == "10.0.0.8"


def test_empty_disk_and_mem_size_are_not_stored(protocol_plugin):
    protocol_plugin.collection_metrics_dict["disk_info_gauge"] = [
        {
            "model_id": "disk",
            "disk_name": "Disk.Bay.0",
            "disk": "",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["memory_info_gauge"] = [
        {
            "model_id": "memory",
            "mem_locator": "DIMM_A1",
            "mem_size": "   ",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        },
        {
            "model_id": "memory",
            "mem_locator": "DIMM_B1",
            "mem_size": 0,
            "self_device": "10.0.0.8",
            "collect_status": "success",
        },
    ]

    protocol_plugin.format_metrics()

    disk = protocol_plugin.result["disk"][0]
    assert disk["inst_name"] == "Disk.Bay.0-10.0.0.8"
    assert "disk" not in disk

    memory_rows = {item["inst_name"]: item for item in protocol_plugin.result["memory"]}
    assert memory_rows["DIMM_A1-10.0.0.8"]["mem_locator"] == "DIMM_A1"
    assert "mem_size" not in memory_rows["DIMM_A1-10.0.0.8"]
    assert memory_rows["DIMM_B1-10.0.0.8"]["mem_locator"] == "DIMM_B1"
    assert "mem_size" not in memory_rows["DIMM_B1-10.0.0.8"]


def test_zero_cpu_core_is_stored(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "cpu_cores": 0,
            "cpu_threads": 0,
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    server = protocol_plugin.result["physcial_server"][0]
    assert server["cpu_core"] == 0
    assert server["cpu_threads"] == 0


def test_unknown_cpu_arch_is_not_stored(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "cpu_arch": "loongarch64",
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    server = protocol_plugin.result["physcial_server"][0]
    assert "cpu_arch" not in server


def test_redfish_p0_fields_map_to_child_instances(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "power_state": "On",
            "health": "OK",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["disk_info_gauge"] = [
        {
            "model_id": "disk",
            "disk_name": "Disk.Bay.0",
            "health": "Warning",
            "disk_life_percent": "88",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["nic_info_gauge"] = [
        {
            "model_id": "nic",
            "nic_mac": "AA:BB:CC:DD:EE:FF",
            "nic_iface": "NIC.Slot.1-1",
            "nic_speed_mbps": "10000",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["storage_controller_info_gauge"] = [
        {
            "model_id": "storage_controller",
            "sc_id": "0",
            "sc_name": "RAID",
            "sc_firmware": "5.1",
            "health": "OK",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]
    protocol_plugin.collection_metrics_dict["psu_info_gauge"] = [
        {
            "model_id": "psu",
            "psu_name": "PSU1",
            "psu_capacity_watts": "1600",
            "health": "OK",
            "PowerInputWatts": "120",
            "self_device": "10.0.0.8",
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    server = protocol_plugin.result["physcial_server"][0]
    assert server["power_state"] == "On"
    assert server["health"] == "OK"

    disk = protocol_plugin.result["disk"][0]
    assert disk["health"] == "Warning"
    assert disk["disk_life_percent"] == 88
    assert disk["inst_name"] == "Disk.Bay.0-10.0.0.8"

    nic = protocol_plugin.result["nic"][0]
    assert nic["nic_iface"] == "NIC.Slot.1-1"
    assert nic["nic_speed_mbps"] == 10000

    controller = protocol_plugin.result["storage_controller"][0]
    assert controller["inst_name"] == "0-10.0.0.8"
    assert controller["sc_firmware"] == "5.1"
    assert controller["assos"][0]["model_asst_id"] == "physcial_server_contains_storage_controller"
    assert controller["assos"][0]["inst_name"] == "10.0.0.8"

    psu = protocol_plugin.result["psu"][0]
    assert psu["inst_name"] == "PSU1-10.0.0.8"
    assert psu["psu_capacity_watts"] == 1600
    assert "PowerInputWatts" not in psu
    assert psu["assos"][0]["model_asst_id"] == "physcial_server_contains_psu"


def test_missing_p0_metrics_still_format_parent(protocol_plugin):
    protocol_plugin.collection_metrics_dict["physcial_server_info_gauge"] = [
        {
            "ip_addr": "10.0.0.8",
            "serial_number": "SERVER-SN-8",
            "collect_status": "success",
        }
    ]

    protocol_plugin.format_metrics()

    assert set(protocol_plugin.result) == {"physcial_server"}
    assert protocol_plugin.result["physcial_server"][0]["inst_name"] == "10.0.0.8"
