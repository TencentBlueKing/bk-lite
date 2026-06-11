from apps.cmdb.collection.collect_plugin.manageone import ManageOneCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


class ManageOneCollectionPlugin(AutoRegisterCollectionPluginMixin, ManageOneCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "manageone"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "manageone_info_gauge",
        "manageone_cloud_info_gauge",
        "manageone_server_info_gauge",
        "manageone_host_info_gauge",
        "manageone_ds_info_gauge",
        "manageone_elb_info_gauge",
    ]

    field_mappings = {
        "manageone": {
            "global_domain_name": "global_domain_name",
            "region": "region",
        },
        "manageone_cloud": {
            "inst_name": ManageOneCollectMetrics.set_instance_inst_name,
            "assos": ManageOneCollectMetrics.asso_cloud,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "cloud_version": "cloud_version",
            "brand": "brand",
            "vcpus": (int, "vcpus"),
            "memory_mb": (int, "memory_mb"),
            "storage_gb": (int, "storage_gb"),
        },
        "manageone_server": {
            "inst_name": ManageOneCollectMetrics.set_instance_inst_name,
            "assos": ManageOneCollectMetrics.asso_server,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "region": "region",
            "status": "status",
            "os_name": "os_name",
            "vcpus": (int, "vcpus"),
            "self_host_ip": "self_host_ip",
            "create_time": "create_time",
            "expired_time": "expired_time",
        },
        "manageone_host": {
            "inst_name": ManageOneCollectMetrics.set_instance_inst_name,
            "assos": ManageOneCollectMetrics.asso_host,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "hypervisor_type": "hypervisor_type",
            "memory_mb": (int, "memory_mb"),
            "vcpus": (int, "vcpus"),
        },
        "manageone_ds": {
            "inst_name": ManageOneCollectMetrics.set_instance_inst_name,
            "assos": ManageOneCollectMetrics.asso_ds,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "storage_gb": (int, "storage_gb"),
        },
        "manageone_elb": {
            "inst_name": ManageOneCollectMetrics.set_instance_inst_name,
            "assos": ManageOneCollectMetrics.asso_elb,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "instance_type": "instance_type",
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
