"""Dell Unity 存储采集插件单元测试（_pure：不依赖 DB/IO）。"""


def test_dell_unity_plugin_contract():
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert DellUnityCollectionPlugin.supported_model_id == "dell_unity"
    assert DellUnityCollectionPlugin.supported_task_type == CollectPluginTypes.CLOUD
    for metric in (
        "storage_info_gauge",
        "storage_pool_info_gauge",
        "storage_disk_info_gauge",
        "storage_volume_info_gauge",
        "storage_eth_port_info_gauge",
        "storage_fc_port_info_gauge",
    ):
        assert metric in DellUnityCollectionPlugin.metric_names


def test_dell_unity_field_mappings_cover_six_models():
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin

    fms = DellUnityCollectionPlugin.field_mappings
    assert set(fms) == {
        "storage",
        "storage_pool",
        "storage_disk",
        "storage_volume",
        "storage_eth_port",
        "storage_fc_port",
    }
    assert "mac" in fms["storage_eth_port"]
    assert "wwpn" in fms["storage_fc_port"]
    assert "wwn" in fms["storage_volume"]
    assert "inst_name" in fms["storage"]


def test_dell_unity_registered_in_registry():
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, "dell_unity")
    assert plugin is DellUnityCollectionPlugin
    assert CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, "storage").__name__ == "OceanStorCollectionPlugin"


def test_dell_unity_in_collect_object_tree():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    entries = [child for group in COLLECT_OBJ_TREE for child in group.get("children", []) if child.get("id") == "dell_unity"]
    assert entries
    assert entries[0]["model_id"] == "dell_unity"
    assert entries[0]["target_model_id"] == "storage"
    assert entries[0]["credential_protocol"] == "dell_unity_https"
    assert entries[0]["credential_default_port"] == 443
    assert "beta" in entries[0]["name"].lower()


def test_dell_unity_bytes_to_gb_and_status():
    from apps.cmdb.collection.collect_plugin.dell_unity import DellUnityCollectMetrics

    assert DellUnityCollectMetrics.bytes_to_gb("1099511627776") == 1024
    assert DellUnityCollectMetrics.bytes_to_gb("") == 0
    assert DellUnityCollectMetrics.norm_status("online") == "running"
    assert DellUnityCollectMetrics.norm_status("up") == "running"
    assert DellUnityCollectMetrics.norm_status("5") == "running"
    assert DellUnityCollectMetrics.norm_status("offline") == "stopped"
    assert DellUnityCollectMetrics.norm_status("") == "stopped"
