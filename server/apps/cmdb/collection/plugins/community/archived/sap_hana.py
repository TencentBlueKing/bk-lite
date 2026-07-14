"""SapHana archived plugin stub —— SAP HANA license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class SapHanaCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "sap_hana"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
