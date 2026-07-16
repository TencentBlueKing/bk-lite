"""H3C CAS 私有云采集 stub plugin — 框架占位,无真实 SDK 实现。

【v5 Task 3.5】2026-07-14
- H3C CAS(H3C Cloud Automation System)是紫光华山私有云 IaaS 平台,本期无 SDK 实现
- 框架占位 plugin,等用户对接真实 REST API
- e2e 走 placeholder 模式:fixture 标 _placeholder_reason=plugin_stub
"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class H3CCASCollectionPlugin(AutoRegisterCollectionPluginMixin):
    """H3C CAS 私有云 stub plugin — 无 metric_names / field_mappings 真实实现。"""
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "h3c_cas"
    plugin_source = "community"
    priority = 1

    # stub:无真实 SDK,只能 placeholder
    metric_names = []
    field_mappings = {}
