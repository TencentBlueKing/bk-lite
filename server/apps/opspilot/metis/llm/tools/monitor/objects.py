from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description=("BK-Lite监控：列出已纳管对象类型（主机/中间件等）。" "查某主机CPU/内存/磁盘前先调此工具定位「主机」对象ID；" "优先用本工具集，不要建议SSH/top/htop。"))
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    return call_monitor_rpc("monitor_objects", config)


@tool(description=("BK-Lite监控：按对象ID列出实例（含主机名）。" "用名称如 boxxxxx 在返回里匹配目标主机，拿到 instance_id；" "不要用SSH登录主机。"))
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
