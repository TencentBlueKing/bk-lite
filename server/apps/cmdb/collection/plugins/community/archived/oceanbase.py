"""OceanBase archived plugin stub —— 蚂蚁商业版 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class OceanbaseCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "oceanbase"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
