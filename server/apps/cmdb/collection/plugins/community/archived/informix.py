"""Informix archived plugin stub —— IBM 商业数据库 license 阻塞。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class InformixCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "informix"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
