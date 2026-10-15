# -- coding: utf-8 --
"""自定义脚本入库。连接协议由插件操作系统决定，写入仍按目标模型。"""

from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import COLLECT_OBJ_TREE, CollectPluginTypes


def target_model_task_type(model_id):
    """目标模型在内置采集树里的任务类型。同一模型有多条入口时优先主机、数据库、中间件。"""

    found = []
    for group in COLLECT_OBJ_TREE:
        for child in group.get("children") or []:
            task_type = child.get("task_type")
            if child.get("model_id") != model_id or not task_type or task_type == CollectPluginTypes.CUSTOM_SCRIPT:
                continue
            found.append(task_type)
    for preferred in (CollectPluginTypes.HOST, CollectPluginTypes.DB, CollectPluginTypes.MIDDLEWARE):
        if preferred in found:
            return preferred
    return found[0] if found else None


class CustomScriptCollect(BaseCollect):
    def get_collect_plugin(self):
        return get_collection_plugin(CollectPluginTypes.CUSTOM_SCRIPT, self.model_id)

    def _should_filter_collect_task(self, model_id):
        family = target_model_task_type(model_id)
        if family == CollectPluginTypes.HOST:
            return model_id == "physcial_server"
        if family is None:
            return super()._should_filter_collect_task(model_id)
        return True
