"""DomesticLinux archived plugin stub —— 国产 Linux 平台约束(无 aarch64 fixture)。"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class DomesticLinuxCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.HOST
    supported_model_id = "domestic_linux"
    plugin_source = "community"
    priority = 1
    metric_names = []
    field_mappings = {}
