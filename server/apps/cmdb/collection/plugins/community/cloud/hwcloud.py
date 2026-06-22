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
        "hwcloud_evs_info_gauge",
        "hwcloud_obs_info_gauge",
        "hwcloud_vpc_info_gauge",
        "hwcloud_subnet_info_gauge",
        "hwcloud_eip_info_gauge",
        "hwcloud_sg_info_gauge",
        "hwcloud_elb_info_gauge",
        "hwcloud_rds_info_gauge",
        "hwcloud_dcs_info_gauge",
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
        "hwcloud_evs": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.asso_evs,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "disk_size": (int, "disk_size"),
            "disk_type": "disk_type",
            "category": "category",
            "status": "status",
            "charge_type": "charge_type",
            "zone": "zone",
            "region": "region",
            "create_time": "create_time",
        },
        "hwcloud_obs": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "bucket_type": "bucket_type",
            "region": "region",
            "create_time": "create_time",
        },
        "hwcloud_vpc": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "status": "status",
            "cidr": "cidr",
            "is_default": "is_default",
            "region": "region",
        },
        "hwcloud_subnet": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.asso_subnet,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "status": "status",
            "cidr": "cidr",
            "gateway": "gateway",
            "zone": "zone",
            "region": "region",
        },
        "hwcloud_eip": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "status": "status",
            "bandwidth": (int, "bandwidth"),
            "charge_type": "charge_type",
            "region": "region",
            "create_time": "create_time",
        },
        "hwcloud_sg": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "is_default": "is_default",
            "region": "region",
        },
        "hwcloud_elb": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "status": "status",
            "ip_version": "ip_version",
            "ipv6_addr": "ipv6_addr",
            "charge_type": "charge_type",
            "region": "region",
            "create_time": "create_time",
        },
        "hwcloud_rds": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "public_ip": "public_ip",
            "status": "status",
            "db_type": "db_type",
            "engine": "engine",
            "engine_version": "engine_version",
            "volume_type": "volume_type",
            "volume_size": (int, "volume_size"),
            "vcpus": (int, "vcpus"),
            "memory_gb": (int, "memory_gb"),
            "port": (int, "port"),
            "region": "region",
            "charge_type": "charge_type",
            "create_time": "create_time",
        },
        "hwcloud_dcs": {
            "inst_name": HwCloudCollectMetrics.set_instance_inst_name,
            "assos": HwCloudCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "ip_addr": "ip_addr",
            "port": (int, "port"),
            "status": "status",
            "engine": "engine",
            "engine_version": "engine_version",
            "capacity_gb": (int, "capacity_gb"),
            "cache_mode": "cache_mode",
            "charge_type": "charge_type",
            "region": "region",
            "create_time": "create_time",
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
