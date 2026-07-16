"""Storm archived plugin stub —— Storm 集群依赖(无单机 fixture)。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class StormCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.PROTOCOL
    supported_model_id = "storm"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
