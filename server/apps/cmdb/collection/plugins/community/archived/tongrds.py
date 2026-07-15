"""TongRds archived plugin stub —— 东方通 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class TongRdsCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "tongrds"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
