from apps.cmdb.collection.collect_plugin.oceanstor import OceanStorCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class OceanStorCollectionPlugin(AutoRegisterCollectionPluginMixin, OceanStorCollectMetrics):
    """华为 OceanStor 存储采集（多对象：storage + 池/磁盘/卷）。"""

    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "storage"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "storage_info_gauge",
        "storage_pool_info_gauge",
        "storage_disk_info_gauge",
        "storage_volume_info_gauge",
    ]

    field_mappings = {
        # 主对象：采集器已产出设备级字段与聚合容量/数量
        "storage": {
            "device_sn": "device_sn",
            "model": "model",
            "brand": "brand",
            "storage_type": "storage_type",
            "firmware_version": "firmware_version",
            "sys_desc": "sys_desc",
            "total_capacity": (OceanStorCollectMetrics.to_int, "total_capacity"),
            "used_capacity": (OceanStorCollectMetrics.to_int, "used_capacity"),
            "available_capacity": (OceanStorCollectMetrics.to_int, "available_capacity"),
            "pool_count": (OceanStorCollectMetrics.to_int, "pool_count"),
            "disk_count": (OceanStorCollectMetrics.to_int, "disk_count"),
            "volume_count": (OceanStorCollectMetrics.to_int, "volume_count"),
            "running_status": OceanStorCollectMetrics.running_status,
        },
        # 存储池（GET /storagepool）
        "storage_pool": {
            "inst_name": OceanStorCollectMetrics.set_child_inst_name,
            "self_device": OceanStorCollectMetrics.self_device,
            "assos": OceanStorCollectMetrics.asso_pool,
            "pool_type": "USAGETYPE",
            "total_capacity": OceanStorCollectMetrics.pool_total_gb,
            "used_capacity": OceanStorCollectMetrics.pool_used_gb,
            "available_capacity": OceanStorCollectMetrics.pool_free_gb,
            "running_status": OceanStorCollectMetrics.running_status,
        },
        # 物理磁盘（GET /disk）
        "storage_disk": {
            "inst_name": OceanStorCollectMetrics.set_disk_inst_name,
            "self_device": OceanStorCollectMetrics.self_device,
            "assos": OceanStorCollectMetrics.asso_disk,
            "slot": "LOCATION",
            "disk_vendor": "MANUFACTURER",
            "disk_model": "MODEL",
            "disk_type": "DISKTYPE",
            "disk_capacity": OceanStorCollectMetrics.disk_capacity_gb,
            "disk_sn": "SERIALNUMBER",
            "rotate_speed": (OceanStorCollectMetrics.to_int, "SPEEDRPM"),
            "running_status": OceanStorCollectMetrics.running_status,
        },
        # 卷/LUN（GET /lun）
        "storage_volume": {
            "inst_name": OceanStorCollectMetrics.set_child_inst_name,
            "self_device": OceanStorCollectMetrics.self_device,
            "assos": OceanStorCollectMetrics.asso_volume,
            "parent_pool": "PARENTNAME",
            "wwn": "WWN",
            "volume_capacity": OceanStorCollectMetrics.volume_capacity_gb,
            "alloc_capacity": OceanStorCollectMetrics.volume_alloc_gb,
            "alloc_type": "ALLOCTYPE",
            "running_status": OceanStorCollectMetrics.running_status,
        },
    }

    @property
    def _metrics(self):
        return list(self.metric_names)

    @property
    def model_field_mapping(self):
        return {
            model_id: bind_collection_mapping(self, mapping)
            for model_id, mapping in self.field_mappings.items()
        }
