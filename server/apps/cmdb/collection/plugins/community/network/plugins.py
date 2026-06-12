from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.constants import NETWORK_COLLECT
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.collection.plugins.base import bind_collection_mapping
from apps.cmdb.constants.constants import CollectPluginTypes


NETWORK_DEVICE_MAPPING = {
    "inst_name": CollectNetworkMetrics.set_inst_name,
    "ip_addr": "ip_addr",
    "soid": "sysobjectid",
    "port": "port",
    "model": "model",
    "brand": "brand",
    "sys_desc": "sysdescr",
    "model_id": "model_id",
}

NETWORK_INTERFACE_MAPPING = {
    "inst_name": CollectNetworkMetrics.set_interface_inst_name,
    "self_device": CollectNetworkMetrics.set_self_device,
    "mac": "mac_address",
    "name": CollectNetworkMetrics.interface_name,
    "status": (CollectNetworkMetrics.set_interface_status, "oper_status"),
    "assos": CollectNetworkMetrics.get_interface_asso,
}


class NetworkCollectionPlugin(AutoRegisterCollectionPluginMixin, CollectNetworkMetrics):
    supported_task_type = CollectPluginTypes.SNMP
    supported_model_id = "network"
    plugin_source = "community"
    priority = 10

    @property
    def _metrics(self):
        return NETWORK_COLLECT

    @property
    def device_map(self):
        return bind_collection_mapping(self, NETWORK_DEVICE_MAPPING)

    @property
    def model_field_mapping(self):
        return bind_collection_mapping(self, NETWORK_INTERFACE_MAPPING)