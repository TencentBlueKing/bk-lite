"""InfluxDB 采集插件单元测试（_pure：不依赖 DB/IO）。

InfluxDB 走协议采集（PROTOCOL/Agentless TCP），对齐 MySQL。
"""
import pytest

MODEL_ATTRS = (
    "inst_name", "ip_addr", "port", "version", "data_dir", "wal_dir",
    "meta_dir", "engine", "http_bind_address", "auth_enabled",
    "https_enabled", "max_concurrent_queries",
)


def test_influxdb_plugin_contract():
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert InfluxdbCollectionPlugin.supported_model_id == "influxdb"
    assert InfluxdbCollectionPlugin.supported_task_type == CollectPluginTypes.PROTOCOL
    assert InfluxdbCollectionPlugin.metric_names == ("influxdb_info_gauge",)


def test_influxdb_field_mapping_covers_model_attrs():
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin

    fm = InfluxdbCollectionPlugin.field_mapping
    for attr in MODEL_ATTRS:
        assert attr in fm, f"field_mapping 缺少模型字段 {attr}"


def test_influxdb_registered_in_registry():
    from apps.cmdb.collection.plugins.community.protocol.influxdb import InfluxdbCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.PROTOCOL, "influxdb")
    assert plugin is InfluxdbCollectionPlugin


def test_influxdb_in_collect_object_tree_with_beta():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    entries = [c for grp in COLLECT_OBJ_TREE for c in grp.get("children", [])
               if c.get("model_id") == "influxdb"]
    assert entries, "COLLECT_OBJ_TREE 中缺少 influxdb"
    entry = entries[0]
    assert entry["task_type"] == "protocol"
    assert "beta" in entry["name"].lower(), f"influxdb 采集名称需带 Beta 标志，实际 {entry['name']!r}"
