from apps.cmdb.collection.collect_plugin.netapp_ontap import NetAppOntapCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class NetAppOntapCollectionPlugin(AutoRegisterCollectionPluginMixin, NetAppOntapCollectMetrics):
    """NetApp ONTAP 存储采集（多对象：storage + 池/磁盘/卷 + 以太口/FC 口）。"""

    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "netapp_ontap"
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
            "inst_name": NetAppOntapCollectMetrics.self_device,
            "device_sn": "device_sn",
            "ip_addr": "ip_addr",
            "model": "model",
            "brand": "brand",
            "storage_type": "storage_type",
            "firmware_version": "firmware_version",
            "sys_desc": "sys_desc",
            "total_capacity": (NetAppOntapCollectMetrics.to_int, "total_capacity"),
            "used_capacity": (NetAppOntapCollectMetrics.to_int, "used_capacity"),
            "available_capacity": (NetAppOntapCollectMetrics.to_int, "available_capacity"),
            "pool_count": (NetAppOntapCollectMetrics.to_int, "pool_count"),
            "disk_count": (NetAppOntapCollectMetrics.to_int, "disk_count"),
            "volume_count": (NetAppOntapCollectMetrics.to_int, "volume_count"),
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
        "storage_pool": {
            "inst_name": NetAppOntapCollectMetrics.set_child_inst_name,
            "self_device": NetAppOntapCollectMetrics.self_device,
            "assos": NetAppOntapCollectMetrics.asso_pool,
            "pool_type": "type",
            "total_capacity": NetAppOntapCollectMetrics.pool_total_gb,
            "used_capacity": NetAppOntapCollectMetrics.pool_used_gb,
            "available_capacity": NetAppOntapCollectMetrics.pool_free_gb,
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
        "storage_disk": {
            "inst_name": NetAppOntapCollectMetrics.set_disk_inst_name,
            "self_device": NetAppOntapCollectMetrics.self_device,
            "assos": NetAppOntapCollectMetrics.asso_disk,
            "slot": "name",
            "disk_vendor": "vendor",
            "disk_model": "model",
            "disk_type": "type",
            "disk_capacity": NetAppOntapCollectMetrics.disk_capacity_gb,
            "disk_sn": "serial_number",
            "rotate_speed": (NetAppOntapCollectMetrics.to_int, "rpm"),
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
        "storage_volume": {
            "inst_name": NetAppOntapCollectMetrics.set_child_inst_name,
            "self_device": NetAppOntapCollectMetrics.self_device,
            "assos": NetAppOntapCollectMetrics.asso_volume,
            "parent_pool": "parent_pool",
            "wwn": "wwn",
            "volume_capacity": NetAppOntapCollectMetrics.volume_capacity_gb,
            "alloc_capacity": NetAppOntapCollectMetrics.volume_alloc_gb,
            "alloc_type": "type",
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
        "storage_eth_port": {
            "inst_name": NetAppOntapCollectMetrics.set_eth_inst_name,
            "self_device": NetAppOntapCollectMetrics.self_device,
            "assos": NetAppOntapCollectMetrics.asso_eth_port,
            "name": NetAppOntapCollectMetrics.set_port_name,
            "location": "node_name",
            "mac": NetAppOntapCollectMetrics.set_eth_mac,
            "ip_addr": NetAppOntapCollectMetrics.set_eth_ip,
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
        "storage_fc_port": {
            "inst_name": NetAppOntapCollectMetrics.set_fc_inst_name,
            "self_device": NetAppOntapCollectMetrics.self_device,
            "assos": NetAppOntapCollectMetrics.asso_fc_port,
            "name": NetAppOntapCollectMetrics.set_port_name,
            "location": "node_name",
            "wwpn": NetAppOntapCollectMetrics.set_fc_wwpn,
            "speed": NetAppOntapCollectMetrics.set_fc_speed,
            "running_status": NetAppOntapCollectMetrics.running_status,
        },
    }

    @property
    def _metrics(self):
        return list(self.metric_names)

    @property
    def model_field_mapping(self):
        return {model_id: bind_collection_mapping(self, mapping) for model_id, mapping in self.field_mappings.items()}
