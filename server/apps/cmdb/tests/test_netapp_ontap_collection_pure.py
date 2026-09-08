"""NetApp ONTAP 存储采集插件单元测试（_pure：不依赖 DB/IO）。"""


def test_netapp_ontap_plugin_contract():
    from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert NetAppOntapCollectionPlugin.supported_model_id == "netapp_ontap"
    assert NetAppOntapCollectionPlugin.supported_task_type == CollectPluginTypes.CLOUD
    for metric in (
        "storage_info_gauge",
        "storage_pool_info_gauge",
        "storage_disk_info_gauge",
        "storage_volume_info_gauge",
        "storage_eth_port_info_gauge",
        "storage_fc_port_info_gauge",
    ):
        assert metric in NetAppOntapCollectionPlugin.metric_names


def test_netapp_ontap_field_mappings_cover_six_models():
    from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin

    fms = NetAppOntapCollectionPlugin.field_mappings
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


def test_netapp_ontap_registered_in_registry():
    from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, "netapp_ontap")
    assert plugin is NetAppOntapCollectionPlugin
    assert CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, "storage").__name__ == "OceanStorCollectionPlugin"


def test_netapp_ontap_in_collect_object_tree():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    entries = [child for group in COLLECT_OBJ_TREE for child in group.get("children", []) if child.get("id") == "netapp_ontap"]
    assert entries
    assert entries[0]["model_id"] == "netapp_ontap"
    assert entries[0]["target_model_id"] == "storage"
    assert entries[0]["credential_protocol"] == "netapp_ontap_https"
    assert entries[0]["credential_default_port"] == 443
    assert "beta" in entries[0]["name"].lower()


def test_netapp_bytes_to_gb_and_status():
    from apps.cmdb.collection.collect_plugin.netapp_ontap import NetAppOntapCollectMetrics

    assert NetAppOntapCollectMetrics.bytes_to_gb("1099511627776") == 1024
    assert NetAppOntapCollectMetrics.bytes_to_gb("") == 0
    assert NetAppOntapCollectMetrics.norm_status("online") == "running"
    assert NetAppOntapCollectMetrics.norm_status("up") == "running"
    assert NetAppOntapCollectMetrics.norm_status("offline") == "stopped"
    assert NetAppOntapCollectMetrics.norm_status("") == "stopped"
