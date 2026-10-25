from apps.cmdb.collection.collect_plugin.vmware import CollectVmwareMetrics
from apps.cmdb.collection.constants import VMWARE_CLUSTER
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes

VMWARE_MODEL_FIELD_MAPPING = {
    "vmware_vc": {
        "vc_version": "vc_version",
        "inst_name": CollectVmwareMetrics.set_vc_inst_name,
    },
    "vmware_vm": {
        "inst_name": "inst_name",
        "ip_addr": "ip_addr",
        "self_vc": CollectVmwareMetrics.set_vc_inst_name,
        "resource_id": "resource_id",
        "os_name": "os_name",
        "vcpus": (int, "vcpus"),
        "memory": (int, "memory"),
        "annotation": "annotation",
        "uptime_seconds": (int, "uptime_seconds"),
        "tools_version": "tools_version",
        "tools_status": "tools_status",
        "tools_running_status": "tools_running_status",
        "last_boot": "last_boot",
        "creation_date": "creation_date",
        "last_backup": "last_backup",
        "backup_policy": "backup_policy",
        "data_disks": CollectVmwareMetrics.set_data_disks,
        "self_esxi": CollectVmwareMetrics.get_vm_esxi_name,
        "assos": CollectVmwareMetrics.get_vm_asso,
    },
    "vmware_esxi": {
        "inst_name": "inst_name",
        "ip_addr": "ip_addr",
        "self_vc": CollectVmwareMetrics.set_vc_inst_name,
        "resource_id": "resource_id",
        "cpu_cores": (int, "cpu_cores"),
        "vcpus": (int, "vcpus"),
        "memory": (int, "memory"),
        "esxi_version": "esxi_version",
        "boot_time": "boot_time",
        "assos": CollectVmwareMetrics.get_esxi_asso,
    },
    "vmware_ds": {
        "inst_name": "inst_name",
        "self_vc": CollectVmwareMetrics.set_vc_inst_name,
        "system_type": "system_type",
        "resource_id": "resource_id",
        "storage": (int, "storage"),
        "url": "ds_url",
    },
}


class VmwareVCCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectVmwareMetrics):
    supported_task_type = CollectPluginTypes.VM
    supported_model_id = "vmware_vc"
    plugin_source = "community"
    priority = 10

    @property
    def _metrics(self):
        return VMWARE_CLUSTER

    @property
    def model_field_mapping(self):
        return {model_id: bind_collection_mapping(self, mapping) for model_id, mapping in VMWARE_MODEL_FIELD_MAPPING.items()}
