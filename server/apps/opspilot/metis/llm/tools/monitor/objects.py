from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error, wrap_success

_MONITOR_OBJECT_SUMMARY_KEYS = ("id", "name", "type", "type_info", "level", "parent", "display_name")
_INSTANCE_KEYWORD_KEYS = ("name", "id", "ip", "instance_id", "instance_name", "cmdb_id")


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


def _summarize_monitor_instances(data: Any) -> Any:
    if not isinstance(data, list):
        return data
    summarized = []
    for item in data:
        if not isinstance(item, dict):
            summarized.append(item)
            continue
        logical_id = item.get("instance_id") or item.get("id")
        row = {"id": logical_id, "name": item.get("name"), "ip": item.get("ip")}
        if item.get("instance_id"):
            row["instance_id"] = item["instance_id"]
        if item.get("cmdb_id"):
            row["cmdb_id"] = item["cmdb_id"]
        summarized.append(row)
    return summarized


def _instance_matches_keyword(item: Dict[str, Any], needle: str) -> bool:
    parts = [str(item.get(key) or "") for key in _INSTANCE_KEYWORD_KEYS]
    facts = item.get("summary_facts")
    if isinstance(facts, dict):
        parts.append(str(facts.get("asset.ip") or ""))
    return needle in " ".join(parts).lower()


@tool(description=("【主机CPU使用率】第1步：列出BK-Lite已纳管监控对象类型，找到「主机」的monitor_obj_id。" "问主机名或IP的CPU/内存/磁盘时必须先调；用平台监控，不要SSH/top/htop。"))
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    result = call_monitor_rpc("monitor_objects", config)
    if not result.get("success"):
        return result
    return wrap_success(_summarize_monitor_objects(result.get("data")))


@tool(
    description=(
        "【主机CPU使用率】第2步：按monitor_obj_id列出实例（含主机名和IP）。" "可用keyword按主机名或IP过滤；匹配得到监控instance_id。后续工具的instance_ids须用监控ID/主机名/IP，禁止CMDB的inst_uuid/_id。"
    )
)
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
    if not result.get("success"):
        return result
    items = result.get("data")
    if not isinstance(items, list):
        return result
    needle = str(keyword or "").strip().lower()
    if needle:
        items = [item for item in items if isinstance(item, dict) and _instance_matches_keyword(item, needle)]
    return wrap_success(_summarize_monitor_instances(items))
