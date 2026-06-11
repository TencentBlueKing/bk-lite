from apps.cmdb.collection.collect_plugin.fusioninsight import FusionInsightCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class FusionInsightCollectionPlugin(AutoRegisterCollectionPluginMixin, FusionInsightCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "fusioninsight"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "fusioninsight_cluster_info_gauge",
        "fusioninsight_host_info_gauge",
    ]

    field_mappings = {
        "fusioninsight_cluster": {
            "inst_name": FusionInsightCollectMetrics.set_instance_inst_name,
            "assos": FusionInsightCollectMetrics.asso_cluster,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
        },
        "fusioninsight_host": {
            "inst_name": FusionInsightCollectMetrics.set_instance_inst_name,
            "assos": FusionInsightCollectMetrics.asso_host,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "vcpus": "vcpus",
            "memory_mb": "memory_mb",
            "storage_gb": "storage_gb",
            "status": "status",
            "os_name": "os_name",
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
