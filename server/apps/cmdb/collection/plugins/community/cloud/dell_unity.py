from apps.cmdb.collection.collect_plugin.dell_unity import DellUnityCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class DellUnityCollectionPlugin(AutoRegisterCollectionPluginMixin, DellUnityCollectMetrics):
    """Dell Unity 存储采集（多对象：storage + 池/磁盘/卷 + 以太口/FC 口）。"""

    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "dell_unity"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "storage_info_gauge",
        "storage_pool_info_gauge",
        "storage_disk_info_gauge",
        "storage_volume_info_gauge",
        "storage_eth_port_info_gauge",
        "storage_fc_port_info_gauge",
    ]

    field_mappings = {
        "storage": {
            "inst_name": DellUnityCollectMetrics.self_device,
            "device_sn": "device_sn",
            "ip_addr": "ip_addr",
            "model": "model",
            "brand": "brand",
            "storage_type": "storage_type",
            "firmware_version": "firmware_version",
            "sys_desc": "sys_desc",
            "total_capacity": (DellUnityCollectMetrics.to_int, "total_capacity"),
            "used_capacity": (DellUnityCollectMetrics.to_int, "used_capacity"),
            "available_capacity": (DellUnityCollectMetrics.to_int, "available_capacity"),
            "pool_count": (DellUnityCollectMetrics.to_int, "pool_count"),
            "disk_count": (DellUnityCollectMetrics.to_int, "disk_count"),
            "volume_count": (DellUnityCollectMetrics.to_int, "volume_count"),
            "running_status": DellUnityCollectMetrics.running_status,
        },
        "storage_pool": {
            "inst_name": DellUnityCollectMetrics.set_child_inst_name,
            "self_device": DellUnityCollectMetrics.self_device,
            "assos": DellUnityCollectMetrics.asso_pool,
            "pool_type": "type",
            "total_capacity": DellUnityCollectMetrics.pool_total_gb,
            "used_capacity": DellUnityCollectMetrics.pool_used_gb,
            "available_capacity": DellUnityCollectMetrics.pool_free_gb,
            "running_status": DellUnityCollectMetrics.running_status,
        },
        "storage_disk": {
            "inst_name": DellUnityCollectMetrics.set_disk_inst_name,
            "self_device": DellUnityCollectMetrics.self_device,
            "assos": DellUnityCollectMetrics.asso_disk,
            "slot": "slotNumber",
            "disk_vendor": "manufacturer",
            "disk_model": "model",
            "disk_type": "diskTechnology",
            "disk_capacity": DellUnityCollectMetrics.disk_capacity_gb,
            "disk_sn": "wwn",
            "rotate_speed": (DellUnityCollectMetrics.to_int, "rpm"),
            "running_status": DellUnityCollectMetrics.running_status,
        },
        "storage_volume": {
            "inst_name": DellUnityCollectMetrics.set_child_inst_name,
            "self_device": DellUnityCollectMetrics.self_device,
            "assos": DellUnityCollectMetrics.asso_volume,
            "parent_pool": "parent_pool",
            "wwn": "wwn",
            "volume_capacity": DellUnityCollectMetrics.volume_capacity_gb,
            "alloc_capacity": DellUnityCollectMetrics.volume_alloc_gb,
            "alloc_type": "type",
            "running_status": DellUnityCollectMetrics.running_status,
        },
        "storage_eth_port": {
            "inst_name": DellUnityCollectMetrics.set_eth_inst_name,
            "self_device": DellUnityCollectMetrics.self_device,
            "assos": DellUnityCollectMetrics.asso_eth_port,
            "name": DellUnityCollectMetrics.set_port_name,
            "location": "storageProcessor",
            "mac": DellUnityCollectMetrics.set_eth_mac,
            "running_status": DellUnityCollectMetrics.running_status,
        },
        "storage_fc_port": {
            "inst_name": DellUnityCollectMetrics.set_fc_inst_name,
            "self_device": DellUnityCollectMetrics.self_device,
            "assos": DellUnityCollectMetrics.asso_fc_port,
            "name": DellUnityCollectMetrics.set_port_name,
            "location": "storageProcessor",
            "wwpn": DellUnityCollectMetrics.set_fc_wwpn,
            "speed": DellUnityCollectMetrics.set_fc_speed,
            "running_status": DellUnityCollectMetrics.running_status,
        },
    }

    @property
    def _metrics(self):
        return list(self.metric_names)

    @property
    def model_field_mapping(self):
        return {model_id: bind_collection_mapping(self, mapping) for model_id, mapping in self.field_mappings.items()}
