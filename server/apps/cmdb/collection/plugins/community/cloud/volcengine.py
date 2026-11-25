from apps.cmdb.collection.collect_plugin.volcengine import VolcengineCollectMetrics
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin, bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes

_DATABASE_FIELDS = {
    "inst_name": VolcengineCollectMetrics.set_instance_inst_name,
    "assos": VolcengineCollectMetrics.set_asso_instances,
    "resource_name": "resource_name",
    "resource_id": "resource_id",
    "region": "region",
    "zone": "zone",
    "vpc": "vpc",
    "ip_addr": "ip_addr",
    "port": (VolcengineCollectMetrics.to_int, "port"),
    "version": "version",
    "status": "status",
    "storage_gb": (VolcengineCollectMetrics.to_int, "storage_gb"),
    "storage_type": "storage_type",
    "charge_type": "charge_type",
    "create_time": (VolcengineCollectMetrics.convert_datetime_format, "create_time"),
    "tag": "tag",
}


class VolcengineAccountCollectionPlugin(AutoRegisterCollectionPluginMixin, VolcengineCollectMetrics):
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "volcengine_account"
    plugin_source = "community"
    priority = 10

    metric_names = [
        "volcengine_ecs_info_gauge",
        "volcengine_clb_info_gauge",
        "volcengine_eip_info_gauge",
        "volcengine_mysql_info_gauge",
        "volcengine_pgsql_info_gauge",
        "volcengine_tos_info_gauge",
    ]

    field_mappings = {
        "volcengine_ecs": {
            "inst_name": VolcengineCollectMetrics.set_instance_inst_name,
            "assos": VolcengineCollectMetrics.set_asso_instances,
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
            "vcpus": (VolcengineCollectMetrics.to_int, "vcpus"),
            "memory_mb": (VolcengineCollectMetrics.to_int, "memory_mb"),
            "charge_type": "charge_type",
            "create_time": (VolcengineCollectMetrics.convert_datetime_format, "create_time"),
            "expired_time": (VolcengineCollectMetrics.convert_datetime_format, "expired_time"),
            "tag": "tag",
        },
        "volcengine_clb": {
            "inst_name": VolcengineCollectMetrics.set_instance_inst_name,
            "assos": VolcengineCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "region": "region",
            "vpc": "vpc",
            "ip_addr": "ip_addr",
            "public_ip": "public_ip",
            "status": "status",
            "type": "type",
            "charge_type": "charge_type",
            "create_time": (VolcengineCollectMetrics.convert_datetime_format, "create_time"),
            "tag": "tag",
        },
        "volcengine_eip": {
            "inst_name": VolcengineCollectMetrics.set_instance_inst_name,
            "assos": VolcengineCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "region": "region",
            "ip_addr": "ip_addr",
            "status": "status",
            "bandwidth": (VolcengineCollectMetrics.to_int, "bandwidth"),
            "instance_type": "bind_instance_type",
            "instance_id": "bind_instance_id",
            "tag": "tag",
        },
        "volcengine_mysql": _DATABASE_FIELDS,
        "volcengine_pgsql": _DATABASE_FIELDS,
        "volcengine_tos": {
            "inst_name": VolcengineCollectMetrics.set_instance_inst_name,
            "assos": VolcengineCollectMetrics.set_asso_instances,
            "resource_name": "resource_name",
            "resource_id": "resource_id",
            "region": "region",
            "location": "location",
            "extranet_endpoint": "extranet_endpoint",
            "intranet_endpoint": "intranet_endpoint",
            "bucket_type": "bucket_type",
            "creation_date": "creation_date",
            "tag": "tag",
        },
    }

    @property
    def _metrics(self):
        return list(self.metric_names)

    @property
    def model_field_mapping(self):
        return {model_id: bind_collection_mapping(self, mapping) for model_id, mapping in self.field_mappings.items()}
