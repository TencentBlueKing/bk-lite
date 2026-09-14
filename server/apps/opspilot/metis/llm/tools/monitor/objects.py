from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error, wrap_success


_MONITOR_OBJECT_SUMMARY_KEYS = ("id", "name", "type", "type_info", "level", "parent", "display_name")


def _summarize_monitor_objects(data: Any) -> Any:
    if not isinstance(data, list):
        return data
    summarized = []
    for item in data:
        if not isinstance(item, dict):
            summarized.append(item)
            continue
        summarized.append({key: item[key] for key in _MONITOR_OBJECT_SUMMARY_KEYS if key in item})
    return summarized


@tool(description=("【主机CPU使用率】第1步：列出BK-Lite已纳管监控对象类型，找到「主机」的monitor_obj_id。" "问主机名xxx的CPU/内存/磁盘时必须先调；用平台监控，不要SSH/top/htop。"))
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    result = call_monitor_rpc("monitor_objects", config)
    if not result.get("success"):
        return result
    return wrap_success(_summarize_monitor_objects(result.get("data")))


@tool(description=("【主机CPU使用率】第2步：按monitor_obj_id列出实例（含主机名）。" "可用keyword按主机名过滤；在结果里匹配得到instance_id；不要SSH登录。"))
def monitor_list_object_instances(
    monitor_obj_id: str,
    keyword: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    result = call_monitor_rpc(
        "monitor_object_instances",
        config,
        monitor_obj_id=monitor_obj_id,
    )
    needle = str(keyword or "").strip().lower()
    if not needle or not result.get("success"):
        return result
    items = result.get("data")
    if not isinstance(items, list):
        return result
    filtered = []
    for item in items:
        if not isinstance(item, dict):
            continue
        blob = " ".join(str(item.get(key) or "") for key in ("name", "id", "instance_id", "instance_name"))
        if needle in blob.lower():
            filtered.append(item)
    return wrap_success(filtered)
