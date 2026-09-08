# -*- coding: utf-8 -*-
"""Dell Unity 存储采集映射测试（无需真机）。"""
import time

STORAGE_NAME = "Unity-10.0.0.20"


def _vm_vector():
    ts = int(time.time()) - 60
    return {
        "result": [
            {
                "metric": {
                    "__name__": "storage_info_gauge",
                    "collect_status": "success",
                    "device_sn": "FNM00123456789",
                    "ip_addr": "10.0.0.20",
                    "model": "Unity 480",
                    "brand": "dell",
                    "storage_type": "SAN",
                    "firmware_version": "5.3.0.0.5.120",
                    "sys_desc": "FNM00123456789",
                    "total_capacity": "1024",
                    "used_capacity": "100",
                    "available_capacity": "924",
                    "pool_count": "1",
                    "disk_count": "1",
                    "volume_count": "1",
                    "state": "online",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_pool_info_gauge",
                    "collect_status": "success",
                    "name": "Pool0",
                    "type": "1",
                    "state": "online",
                    "sizeTotal": "1099511627776",
                    "sizeUsed": "107374182400",
                    "sizeFree": "992137445376",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_disk_info_gauge",
                    "collect_status": "success",
                    "name": "DPE Disk 0",
                    "model": "MZILS3T8HMLH0D3",
                    "manufacturer": "SAMSUNG",
                    "wwn": "5002538E00000001",
                    "diskTechnology": "1",
                    "rawSize": "3840755982336",
                    "slotNumber": "0",
                    "rpm": "0",
                    "state": "online",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_volume_info_gauge",
                    "collect_status": "success",
                    "name": "lun1",
                    "parent_pool": "Pool0",
                    "wwn": "60:06:01:60:12:34:56:78:12:34:56:78:9A:BC:DE:F0",
                    "sizeTotal": "107374182400",
                    "sizeAllocated": "53687091200",
                    "type": "1",
                    "state": "online",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_eth_port_info_gauge",
                    "collect_status": "success",
                    "name": "SP A Ethernet Port 0",
                    "storageProcessor": "SP A",
                    "macAddress": "00:60:16:aa:bb:01",
                    "state": "up",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_eth_port_info_gauge",
                    "collect_status": "success",
                    "name": "SP A Ethernet Port 1",
                    "storageProcessor": "SP A",
                    "macAddress": "",
                    "state": "down",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_fc_port_info_gauge",
                    "collect_status": "success",
                    "name": "SP A FC Port 0",
                    "storageProcessor": "SP A",
                    "wwn": "50:06:01:60:88:60:32:8D",
                    "currentSpeed": "16",
                    "state": "up",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_fc_port_info_gauge",
                    "collect_status": "success",
                    "name": "SP A FC Port 1",
                    "storageProcessor": "SP A",
                    "wwn": "",
                    "state": "down",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name=STORAGE_NAME):
    from apps.cmdb.collection.collect_plugin.dell_unity import DellUnityCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin

    class _FakeInst:
        model_id = "dell_unity"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(DellUnityCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return DellUnityCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9701)


def test_dell_unity_storage_main_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    storage = runner.result["storage"][0]
    assert storage["inst_name"] == STORAGE_NAME
    assert storage["device_sn"] == "FNM00123456789"
    assert storage["ip_addr"] == "10.0.0.20"
    assert storage["brand"] == "dell"
    assert storage["storage_type"] == "SAN"
    assert storage["total_capacity"] == 1024
    assert storage["running_status"] == "running"


def test_dell_unity_pool_disk_volume_assoc(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    pool = runner.result["storage_pool"][0]
    assert pool["inst_name"] == f"{STORAGE_NAME}/Pool0"
    assert pool["total_capacity"] == 1024
    assert pool["assos"][0]["model_asst_id"] == "storage_pool_belong_storage"
    disk = runner.result["storage_disk"][0]
    assert disk["inst_name"] == f"{STORAGE_NAME}/0|MZILS3T8HMLH0D3"
    assert disk["disk_sn"] == "5002538E00000001"
    volume = runner.result["storage_volume"][0]
    assert volume["inst_name"] == f"{STORAGE_NAME}/lun1"
    assert volume["wwn"] == "60:06:01:60:12:34:56:78:12:34:56:78:9A:BC:DE:F0"
    asst_ids = {item["model_asst_id"]: item for item in volume["assos"]}
    assert "storage_volume_belong_storage" in asst_ids
    assert asst_ids["storage_volume_belong_storage_pool"]["inst_name"] == f"{STORAGE_NAME}/Pool0"


def test_dell_unity_ports_skip_empty_and_write_contains(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    eth_ports = runner.result["storage_eth_port"]
    assert [item["inst_name"] for item in eth_ports] == ["00:60:16:aa:bb:01"]
    assert eth_ports[0]["mac"] == "00:60:16:aa:bb:01"
    assert eth_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_eth_port"
    assert all("interface_connect" not in item["model_asst_id"] for item in eth_ports[0]["assos"])

    fc_ports = runner.result["storage_fc_port"]
    assert [item["inst_name"] for item in fc_ports] == ["50:06:01:60:88:60:32:8d"]
    assert fc_ports[0]["wwpn"] == "50:06:01:60:88:60:32:8d"
    assert fc_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_fc_port"
