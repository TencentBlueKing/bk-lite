"""ZStack 私有云采集 stub plugin — 框架占位,无真实 SDK 实现。

【v5 Task 3.4】2026-07-14
- zstack 是国产私有云 IaaS 平台,本期无 SDK 实现,只占位注册 plugin 类以便 e2e 走 generic pipeline
- e2e 走 placeholder 模式:fixture 标 _placeholder_reason=plugin_stub
- 下期 follow-up:对接 ZStack API SDK,补真实采集逻辑
"""
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class ZStackCollectionPlugin(AutoRegisterCollectionPluginMixin):
    """ZStack 私有云 stub plugin — 无 metric_names / field_mappings 真实实现。"""
    supported_task_type = CollectPluginTypes.CLOUD
    supported_model_id = "zstack"
    plugin_source = "community"
    priority = 1

    # stub:无真实 SDK,只能 placeholder
    metric_names = []
    field_mappings = {}
