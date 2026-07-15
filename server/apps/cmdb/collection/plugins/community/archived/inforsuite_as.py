"""InforsuiteAS archived plugin stub —— 国产中间件 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class InforsuiteAsCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "inforsuite_as"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
