"""IHS archived plugin stub —— IBM HTTP Server license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class IhsCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "ihs"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
