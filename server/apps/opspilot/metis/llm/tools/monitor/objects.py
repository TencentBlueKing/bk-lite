from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description=("【主机CPU使用率】第1步：列出BK-Lite已纳管监控对象类型，找到「主机」的monitor_obj_id。" "问主机名xxx的CPU/内存/磁盘时必须先调；用平台监控，不要SSH/top/htop。"))
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    return call_monitor_rpc("monitor_objects", config)


@tool(description=("【主机CPU使用率】第2步：按monitor_obj_id列出实例（含主机名）。" "在结果里用名称匹配如boxxxxx，得到instance_id；不要SSH登录。"))
def monitor_list_object_instances(
    monitor_obj_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    return call_monitor_rpc(
        "monitor_object_instances",
        config,
        monitor_obj_id=monitor_obj_id,
    )
