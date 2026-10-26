from apps.cmdb.collection.collect_plugin.hyperv import CollectHypervMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes

HYPERV_CLUSTER = ["hyperv_host_info_gauge", "hyperv_vm_info_gauge"]

HYPERV_MODEL_FIELD_MAPPING = {
    "hyperv_host": {
        "inst_name": CollectHypervMetrics.set_host_inst_name,
        "ip_addr": "ip_addr",
        "resource_id": "resource_id",
        "cpu_cores": (int, "cpu_cores"),
        "memory": (int, "memory"),
        "hyperv_version": "hyperv_version",
    },
    "hyperv_vm": {
        "inst_name": CollectHypervMetrics.set_inst_name,
        "ip_addr": "ip_addr",
        "resource_id": "resource_id",
        "power_state": "power_state",
        "vcpus": (int, "vcpus"),
        "memory": (int, "memory"),
        "self_host": "self_host",
        "assos": CollectHypervMetrics.get_vm_asso,
    },
}


class HypervHostCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectHypervMetrics):
    supported_task_type = CollectPluginTypes.VM
    supported_model_id = "hyperv_host"
    plugin_source = "community"
    priority = 10

    @property
    def _metrics(self):
        return HYPERV_CLUSTER

    @property
    def model_field_mapping(self):
        return {model_id: bind_collection_mapping(self, mapping) for model_id, mapping in HYPERV_MODEL_FIELD_MAPPING.items()}
