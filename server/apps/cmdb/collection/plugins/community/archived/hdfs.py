"""Hdfs archived plugin stub —— HDFS 集群依赖(无单机 fixture)。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class HdfsCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.PROTOCOL
    supported_model_id = "hdfs"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
