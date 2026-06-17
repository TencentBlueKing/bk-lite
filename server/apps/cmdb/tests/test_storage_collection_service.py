# -*- coding: utf-8 -*-
"""华为 OceanStor 存储采集 端到端/服务测试（多对象，无需真机）。

用 Dorado 5000 V6 真实字段名与样本值构造 VM 向量，验证：
- 容量扇区→GB 归一化；RUNNINGSTATUS 码→opera_status；
- 子对象 inst_name 拼接所属存储名防冲突；
- 关联：池/磁盘/卷 belong storage；卷 belong 所属池。
"""
import time

import pytest

STORAGE_NAME = "华为存储-172.24.191.98"


def _vm_vector():
    ts = int(time.time()) - 60
    return {
        "result": [
            {
                "metric": {
                    "__name__": "storage_info_gauge",
                    "collect_status": "success",
                    "device_sn": "2102355TJUN0S1100017",
                    "model": "Dorado 5000 V6",
                    "brand": "huawei",
                    "storage_type": "SAN",
                    "firmware_version": "6.1.8",
                    "sys_desc": "OceanStor Dorado",
                    "total_capacity": "1024",
                    "used_capacity": "100",
                    "available_capacity": "924",
                    "pool_count": "1",
                    "disk_count": "16",
                    "volume_count": "3",
                    "RUNNINGSTATUS": "27",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_pool_info_gauge",
                    "collect_status": "success",
                    "NAME": "StoragePool001",
                    "USAGETYPE": "1",
                    "USERTOTALCAPACITY": "2147483648",      # ×512 = 1 TiB → 1024 GB
                    "USERCONSUMEDCAPACITY": "214748364",
                    "USERFREECAPACITY": "1932735283",
                    "SECTORSIZE": "512",
                    "RUNNINGSTATUS": "27",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_disk_info_gauge",
                    "collect_status": "success",
                    "LOCATION": "CTE0.0",
                    "MODEL": "HSSD-D7K94DN7T6V",
                    "MANUFACTURER": "HUAWEI",
                    "SERIALNUMBER": "SN12345",
                    "DISKTYPE": "SSD",
                    "SECTORS": "15002931200",               # ×512 /1024^3 → 7153 GB
                    "SECTORSIZE": "512",
                    "SPEEDRPM": "0",
                    "RUNNINGSTATUS": "27",
                },
                "value": [ts, "1"],
            },
            {
                "metric": {
                    "__name__": "storage_volume_info_gauge",
                    "collect_status": "success",
                    "NAME": "aSV_Cluster01_LUN001",
                    "WWN": "6abcdef0123456789",
                    "CAPACITY": "2147483648",               # → 1024 GB
                    "ALLOCCAPACITY": "1073741824",          # → 512 GB
                    "ALLOCTYPE": "1",
                    "PARENTNAME": "StoragePool001",
                    "SECTORSIZE": "512",
                    "RUNNINGSTATUS": "27",
                },
                "value": [ts, "1"],
            },
        ]
    }


def _make_runner(monkeypatch, inst_name=STORAGE_NAME):
    from apps.cmdb.collection.collect_plugin.oceanstor import OceanStorCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin

    class _FakeInst:
        model_id = "storage"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(OceanStorCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return OceanStorCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9301)


@pytest.mark.django_db
def test_storage_main_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    s = runner.result["storage"][0]
    assert s["device_sn"] == "2102355TJUN0S1100017"
    assert s["model"] == "Dorado 5000 V6"
    assert s["brand"] == "huawei"
    assert s["total_capacity"] == 1024          # int
    assert s["pool_count"] == 1
    assert s["disk_count"] == 16
    assert s["volume_count"] == 3
    assert s["running_status"] == "running"     # 27 → opera_status


@pytest.mark.django_db
def test_storage_pool_normalization_and_assoc(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    pool = runner.result["storage_pool"][0]
    # inst_name 拼接所属存储名防冲突
    assert pool["inst_name"] == f"{STORAGE_NAME}/StoragePool001"
    assert pool["self_device"] == STORAGE_NAME
    # 容量扇区→GB
    assert pool["total_capacity"] == 1024
    assert pool["running_status"] == "running"
    # belong storage
    assert pool["assos"] == [{
        "model_id": "storage",
        "inst_name": STORAGE_NAME,
        "asst_id": "belong",
        "model_asst_id": "storage_pool_belong_storage",
    }]


@pytest.mark.django_db
def test_storage_disk_fields(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    disk = runner.result["storage_disk"][0]
    assert disk["inst_name"] == f"{STORAGE_NAME}/CTE0.0|HSSD-D7K94DN7T6V"
    assert disk["slot"] == "CTE0.0"
    assert disk["disk_model"] == "HSSD-D7K94DN7T6V"
    assert disk["disk_sn"] == "SN12345"
    assert disk["disk_vendor"] == "HUAWEI"
    assert disk["disk_capacity"] == 7153        # 15002931200×512 /1024^3
    assert disk["rotate_speed"] == 0
    assert disk["assos"][0]["model_asst_id"] == "storage_disk_belong_storage"


@pytest.mark.django_db
def test_storage_volume_belong_pool(monkeypatch):
    runner = _make_runner(monkeypatch)
    runner.format_data(_vm_vector())
    runner.format_metrics()

    vol = runner.result["storage_volume"][0]
    assert vol["inst_name"] == f"{STORAGE_NAME}/aSV_Cluster01_LUN001"
    assert vol["wwn"] == "6abcdef0123456789"
    assert vol["volume_capacity"] == 1024
    assert vol["alloc_capacity"] == 512
    assert vol["parent_pool"] == "StoragePool001"
    # 卷 belong storage + belong 所属池
    asst_ids = {a["model_asst_id"]: a for a in vol["assos"]}
    assert "storage_volume_belong_storage" in asst_ids
    assert "storage_volume_belong_storage_pool" in asst_ids
    assert asst_ids["storage_volume_belong_storage_pool"]["inst_name"] == f"{STORAGE_NAME}/StoragePool001"
