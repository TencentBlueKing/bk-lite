"""存储设备(华为OceanStor)采集插件单元测试（_pure：不依赖 DB/IO）。

存储走多对象采集（CLOUD task_type，复用云家族多对象机制，对齐 SmartX）：
主对象 storage + 子对象 storage_pool/storage_disk/storage_volume。
"""
import pytest


def test_storage_plugin_contract():
    from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert OceanStorCollectionPlugin.supported_model_id == "storage"
    assert OceanStorCollectionPlugin.supported_task_type == CollectPluginTypes.CLOUD
    for m in ("storage_info_gauge", "storage_pool_info_gauge",
              "storage_disk_info_gauge", "storage_volume_info_gauge"):
        assert m in OceanStorCollectionPlugin.metric_names


def test_storage_field_mappings_cover_four_models():
    from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin

    fms = OceanStorCollectionPlugin.field_mappings
    assert set(fms) == {"storage", "storage_pool", "storage_disk", "storage_volume"}
    # 子对象关键字段
    assert "self_device" in fms["storage_pool"]
    assert "disk_sn" in fms["storage_disk"]
    assert "wwn" in fms["storage_volume"]
    assert "parent_pool" in fms["storage_volume"]


def test_storage_registered_in_registry():
    from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, "storage")
    assert plugin is OceanStorCollectionPlugin


def test_storage_in_collect_object_tree_with_beta():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    entries = [c for grp in COLLECT_OBJ_TREE for c in grp.get("children", [])
               if c.get("model_id") == "storage"]
    assert entries, "COLLECT_OBJ_TREE 中缺少 storage"
    assert "beta" in entries[0]["name"].lower()


def test_capacity_sectors_to_gb():
    """OceanStor 容量是扇区数，需 ×SECTORSIZE 归一化为 GB(int)。"""
    from apps.cmdb.collection.collect_plugin.oceanstor import OceanStorCollectMetrics

    # 2147483648 扇区 × 512 字节 = 1 TiB = 1024 GiB
    assert OceanStorCollectMetrics.sectors_to_gb("2147483648", "512") == 1024
    # 空值/异常 → 0
    assert OceanStorCollectMetrics.sectors_to_gb("", "512") == 0
    assert OceanStorCollectMetrics.sectors_to_gb("abc", "512") == 0


def test_running_status_normalization():
    """HEALTHSTATUS/RUNNINGSTATUS 数字码归一化到公共库 opera_status。"""
    from apps.cmdb.collection.collect_plugin.oceanstor import OceanStorCollectMetrics

    assert OceanStorCollectMetrics.norm_status("27") == "running"   # 在线
    assert OceanStorCollectMetrics.norm_status("28") == "stopped"   # 离线
    assert OceanStorCollectMetrics.norm_status("") == "stopped"     # 未知兜底
