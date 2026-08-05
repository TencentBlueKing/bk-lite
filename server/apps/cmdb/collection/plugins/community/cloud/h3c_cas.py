"""华三 UIS (h3c_cas) 社区占位 — 真实采集在企业版 cmdb_enterprise.collect.h3c_cas。

社区保留注册位与 e2e placeholder；企业版 priority=20 覆盖本 stub。
"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class H3CCASCollectionPlugin(AutoRegisterCollectionPluginMixin):
    """社区 stub：无 metric_names / field_mappings；企业版实现 UIS REST 采集。"""
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "h3c_cas"
    plugin_source = "community"
    priority = 1

    metric_names = []
    field_mappings = {}
