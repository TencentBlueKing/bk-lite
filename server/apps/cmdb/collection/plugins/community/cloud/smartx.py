from apps.cmdb.collection.collect_plugin.smartx import SmartXCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class SmartXCollectionPlugin(AutoRegisterCollectionPluginMixin, SmartXCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "smartx"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "smartx_info_gauge",
        "smartx_cluster_info_gauge",
        "smartx_host_info_gauge",
        "smartx_vm_info_gauge",
        "smartx_vmvolume_info_gauge",
    ]

    field_mappings = {
        "smartx": {
            "global_domain_name": "global_domain_name",
        },
        "smartx_cluster": {
            "inst_name": SmartXCollectMetrics.set_instance_inst_name,
            "assos": SmartXCollectMetrics.asso_cluster,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "cluster_type": "cluster_type",
            "cpu_vendor": "cpu_vendor",
            "hypervisor": "hypervisor",
            "version": "version",
            "datacenter": "datacenter",
            "storage_gb": (SmartXCollectMetrics.to_int, "storage_gb"),
            "cache_gb": (SmartXCollectMetrics.to_int, "cache_gb"),
            "vcpus": (SmartXCollectMetrics.to_int, "vcpus"),
            "memory_mb": (SmartXCollectMetrics.to_int, "memory_mb"),
        },
        "smartx_host": {
            "inst_name": SmartXCollectMetrics.set_instance_inst_name,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "data_ip": "data_ip",
            "cpu_brand": "cpu_brand",
            "cpu_arch": "cpu_arch",
            "cpu_sockets": (SmartXCollectMetrics.to_int, "cpu_sockets"),
            "storage_gb": (SmartXCollectMetrics.to_int, "storage_gb"),
            "cache_gb": (SmartXCollectMetrics.to_int, "cache_gb"),
            "vcpus": (SmartXCollectMetrics.to_int, "vcpus"),
            "memory_mb": (SmartXCollectMetrics.to_int, "memory_mb"),
        },
        "smartx_vm": {
            "inst_name": SmartXCollectMetrics.set_instance_inst_name,
            "assos": SmartXCollectMetrics.asso_vm,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "status": "status",
            "vcpus": (SmartXCollectMetrics.to_int, "vcpus"),
            "memory_mb": (SmartXCollectMetrics.to_int, "memory_mb"),
            "ip_addr": "ip_addr",
            "os": "os",
        },
        "smartx_vmvolume": {
            "inst_name": SmartXCollectMetrics.set_instance_inst_name,
            "assos": SmartXCollectMetrics.asso_vmvolume,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "storage_gb": (SmartXCollectMetrics.to_int, "storage_gb"),
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
