from apps.cmdb.collection.collect_plugin.openstack import OpenStackCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class OpenStackCollectionPlugin(AutoRegisterCollectionPluginMixin, OpenStackCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "openstack"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "openstack_info_gauge",
        "openstack_node_info_gauge",
        "openstack_vm_info_gauge",
        "openstack_sp_info_gauge",
        "openstack_vg_info_gauge",
    ]

    field_mappings = {
        "openstack": {
            "global_domain_name": "global_domain_name",
        },
        "openstack_node": {
            "inst_name": OpenStackCollectMetrics.set_instance_inst_name,
            "assos": OpenStackCollectMetrics.asso_node,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "ram_mb": (int, "ram_mb"),
            "vcpus": (int, "vcpus"),
            "disk_gb": (int, "disk_gb"),
        },
        "openstack_vm": {
            "inst_name": OpenStackCollectMetrics.set_instance_inst_name,
            "assos": OpenStackCollectMetrics.asso_vm,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "ram_mb": "ram_mb",
            "vcpus": "vcpus",
            "disk_gb": "disk_gb",
            "status": "status",
            "os_name": "os_name",
            "zone": "zone",
            "region": "region",
            "project_name": "project_name",
        },
        "openstack_sp": {
            "inst_name": OpenStackCollectMetrics.set_instance_inst_name,
            "assos": OpenStackCollectMetrics.asso_sp,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "size_gb": (int, "size_gb"),
            "region": "region",
            "project_name": "project_name",
            "storage_protocol": "storage_protocol",
            "driver_version": "driver_version",
        },
        "openstack_vg": {
            "inst_name": OpenStackCollectMetrics.set_instance_inst_name,
            "assos": OpenStackCollectMetrics.asso_vg,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "size_gb": (int, "size_gb"),
            "zone": "zone",
            "region": "region",
            "project_name": "project_name",
            "status": "status",
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
