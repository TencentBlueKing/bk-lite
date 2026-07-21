"""Oscar archived plugin stub —— 神州通用数据库 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class OscarCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "oscar"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
