from apps.cmdb.collection.collect_plugin.hwcloud import HwCloudCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class HwCloudCollectionPlugin(AutoRegisterCollectionPluginMixin, HwCloudCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "hwcloud"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "hwcloud_info_gauge",
        "hwcloud_ecs_info_gauge",
    ]

    field_mappings = {
        "hwcloud": {
            "endpoint": "endpoint",
        },
        "hwcloud_ecs": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "public_ip": "public_ip",
            "region": "region",
            "zone": "zone",
            "vpc": "vpc",
            "status": "status",
            "instance_type": "instance_type",
            "os_name": "os_name",
            "vcpus": (int, "vcpus"),
            "memory_mb": (int, "memory_mb"),
            "charge_type": "charge_type",
            "create_time": "create_time",
            "expired_time": "expired_time",
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
