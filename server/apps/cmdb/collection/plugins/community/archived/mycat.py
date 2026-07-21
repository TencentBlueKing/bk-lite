"""Mycat archived plugin stub —— Mycat 中间件依赖 MySQL 集群,单 fixture 跑不通。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class MycatCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.HOST
    supported_model_id = "mycat"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
