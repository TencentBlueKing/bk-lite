# -*- coding: utf-8 -*-
"""NetApp ONTAP 存储采集映射测试（无需真机）。"""
import time

STORAGE_NAME = "NetApp-10.0.0.10"


def _vm_vector():
    ts = int(time.time()) - 60
    return {
        "result": [
            {
                "metric": {
                    "__name__": "storage_info_gauge",
                    "collect_status": "success",
                    "device_sn": "1cd8a442-86d1-11e0-ae1c-123478563412",
                    "ip_addr": "10.0.0.10",
                    "model": "AFF-A400",
                    "brand": "netapp",
                    "storage_type": "unified",
                    "firmware_version": "NetApp Release 9.13.1P1",
                    "sys_desc": "cluster1",
                    "total_capacity": "1024",
                    "used_capacity": "100",
                    "available_capacity": "924",
                    "pool_count": "1",
                    "disk_count": "1",
                    "volume_count": "3",
                    "state": "online",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_pool_info_gauge",
                    "collect_status": "success",
                    "name": "aggr1",
                    "state": "online",
                    "total_bytes": "1099511627776",
                    "used_bytes": "107374182400",
                    "available_bytes": "992137445376",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_disk_info_gauge",
                    "collect_status": "success",
                    "name": "1.0.1",
                    "model": "X377_S163A3T8ATE",
                    "vendor": "NETAPP",
                    "serial_number": "S3Z1NX0M",
                    "type": "ssd",
                    "usable_size": "3840755982336",
                    "rpm": "0",
                    "state": "present",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_volume_info_gauge",
                    "collect_status": "success",
                    "name": "vol1",
                    "parent_pool": "aggr1",
                    "wwn": "",
                    "size": "107374182400",
                    "used": "53687091200",
                    "type": "rw",
                    "state": "online",
                    "kind": "volume",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_eth_port_info_gauge",
                    "collect_status": "success",
                    "name": "e0a",
                    "node_name": "node1",
                    "mac_address": "00:0c:29:aa:bb:01",
                    "ip_addr": "10.0.0.10",
                    "state": "up",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_eth_port_info_gauge",
                    "collect_status": "success",
                    "name": "e0b",
                    "node_name": "node1",
                    "mac_address": "",
                    "state": "down",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_fc_port_info_gauge",
                    "collect_status": "success",
                    "name": "0c",
                    "node_name": "node1",
                    "wwpn": "50:0a:09:81:80:11:22:33",
                    "speed": "16",
                    "state": "online",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_fc_port_info_gauge",
                    "collect_status": "success",
                    "name": "0d",
                    "node_name": "node1",
                    "wwpn": "",
                    "state": "offline",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name=STORAGE_NAME):
    from apps.cmdb.collection.collect_plugin.netapp_ontap import NetAppOntapCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin

    class _FakeInst:
        model_id = "netapp_ontap"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(NetAppOntapCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return NetAppOntapCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9501)


def test_netapp_storage_main_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    storage = runner.result["storage"][0]
    assert storage["inst_name"] == STORAGE_NAME
    assert storage["device_sn"] == "1cd8a442-86d1-11e0-ae1c-123478563412"
    assert storage["ip_addr"] == "10.0.0.10"
    assert storage["brand"] == "netapp"
    assert storage["storage_type"] == "unified"
    assert storage["total_capacity"] == 1024
    assert storage["running_status"] == "running"


def test_netapp_pool_disk_volume_assoc(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    pool = runner.result["storage_pool"][0]
    assert pool["inst_name"] == f"{STORAGE_NAME}/aggr1"
    assert pool["total_capacity"] == 1024
    assert pool["assos"][0]["model_asst_id"] == "storage_pool_belong_storage"
    disk = runner.result["storage_disk"][0]
    assert disk["inst_name"] == f"{STORAGE_NAME}/1.0.1|X377_S163A3T8ATE"
    assert disk["disk_sn"] == "S3Z1NX0M"
    volume = runner.result["storage_volume"][0]
    assert volume["inst_name"] == f"{STORAGE_NAME}/vol1"
    assert volume["wwn"] == ""
    asst_ids = {item["model_asst_id"]: item for item in volume["assos"]}
    assert "storage_volume_belong_storage" in asst_ids
    assert asst_ids["storage_volume_belong_storage_pool"]["inst_name"] == f"{STORAGE_NAME}/aggr1"


def test_netapp_ports_skip_empty_and_write_contains(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    eth_ports = runner.result["storage_eth_port"]
    assert [item["inst_name"] for item in eth_ports] == ["00:0c:29:aa:bb:01"]
    assert eth_ports[0]["mac"] == "00:0c:29:aa:bb:01"
    assert eth_ports[0]["ip_addr"] == "10.0.0.10"
    assert eth_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_eth_port"
    assert all("interface_connect" not in item["model_asst_id"] for item in eth_ports[0]["assos"])

    fc_ports = runner.result["storage_fc_port"]
    assert [item["inst_name"] for item in fc_ports] == ["50:0a:09:81:80:11:22:33"]
    assert fc_ports[0]["wwpn"] == "50:0a:09:81:80:11:22:33"
    assert fc_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_fc_port"
