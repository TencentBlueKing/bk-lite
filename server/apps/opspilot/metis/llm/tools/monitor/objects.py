from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error, wrap_success

_MONITOR_OBJECT_SUMMARY_KEYS = ("id", "name", "type", "type_info", "level", "parent", "display_name")
_INSTANCE_KEYWORD_KEYS = ("name", "id", "ip", "instance_id", "instance_name", "cmdb_id")
_OBJECT_TYPE_CHOICE_HINT = (
    "用户只给了实例名、未说明对象类型时：禁止根据名称形态猜测 Host、K8s Pod 或中间件。"
    "必须立即调用 request_user_choice（question_type=single_select），"
    "options 必须放入 monitor_list_objects 返回的全部真实对象 name，不要截断、不要改用 text、不要在对话里列出类型。"
    "用户已明确说是主机/Host、Pod 或中间件时，不要 request_user_choice，直接用对应对象 id 列实例。"
)
_EMPTY_INSTANCE_NEXT_HINT = (
    "禁止猜测、递增或改换 monitor_obj_id 重试，禁止截断名称按台循环。"
    "用户未声明类型时 request_user_choice（single_select）问对象类型；"
    "用户已声明主机/Pod/中间件时不要再问，把空列表当该类型下无匹配实例。"
)
_UNMATCHED_INSTANCE_KEYWORD_MESSAGE = (
    "该 monitor_obj_id 下未匹配 keyword。"
    "禁止猜测、递增或改换 monitor_obj_id 重试，禁止截断名称按台循环。"
    "用户未声明类型时不要把空列表当成最终结论，request_user_choice（single_select）问对象类型，"
    "options 用 monitor_list_objects 返回的全部对象类型名，禁止纯文本列出。"
    "用户已声明主机/Pod/中间件时不要再问类型，把空列表当该类型下无匹配实例。"
)
_EMPTY_INSTANCE_OBJECT_MESSAGE = (
    "该 monitor_obj_id 下没有实例。禁止猜测其他 ID。"
    "用户未声明类型时不要把空列表当成最终结论，request_user_choice（single_select）问对象类型，"
    "options 用 monitor_list_objects 返回的全部对象类型名。"
    "用户已声明类型时不要再问，把空列表当该类型下无此实例。"
)


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


def _instance_rows(data: Any) -> list:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "results", "instances"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _object_type_labels(data: Any, *, limit: int = 12) -> list:
    labels = []
    seen = set()
    if not isinstance(data, list):
        return labels
    for item in data:
        if not isinstance(item, dict):
            continue
        label = str(item.get("name") or item.get("display_name") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _ask_object_type_hint(data: Any) -> str:
    labels = _object_type_labels(data, limit=200)
    if not labels:
        return _OBJECT_TYPE_CHOICE_HINT
    if len(labels) == 1:
        return f"{_OBJECT_TYPE_CHOICE_HINT}当前只有一类对象：{labels[0]}，可直接使用其 id。"
    count_line = f"本次共 {len(labels)} 类对象。"
    if len(labels) <= 8:
        count_line += f"当前对象类型：{'、'.join(labels)}。"
    return f"{_OBJECT_TYPE_CHOICE_HINT}{count_line}用 single_select，options 必须包含 data 中每一条 name，不要截断，不要用 text。"


def _available_instance_names(items: list, *, limit: int = 20) -> list:
    names = []
    seen = set()
    for item in items:
        label = str(item.get("name") or item.get("ip") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        names.append(label)
        if len(names) >= limit:
            break
    return names


def _instance_ids_for_query(items: list, *, limit: int = 8) -> list:
    ids = []
    seen = set()
    for item in items:
        value = str(item.get("instance_id") or item.get("id") or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)
        if len(ids) >= limit:
            break
    return ids


def _instance_query_hint(items: list) -> str:
    ids = _instance_ids_for_query(items)
    if not ids:
        return "后续查时序的 instance_ids 必须用本列表的 instance_id，禁止用 name 或 IP 代替。"
    shown = "、".join(ids)
    extra = " 等" if len(items) > len(ids) else ""
    return (
        f"后续 monitor_query_metric_data / monitor_list_instance_metrics 的 instance_ids 必须用本列表 instance_id（{shown}{extra}），"
        "禁止用 name 或 IP 代替，禁止 CMDB 的 inst_uuid/_id。"
    )


@tool(
    description=(
        "【主机CPU使用率】第1步：列出BK-Lite已纳管监控对象类型，得到各类型 monitor_obj_id。"
        "问主机名或IP的CPU/内存/磁盘时必须先调；用平台监控，不要SSH/top/htop。"
        "用户未说明是主机/Pod/中间件时，禁止按名称猜类型；列出后必须 request_user_choice。"
        "用户已声明类型时不要再问，直接用对应 id。"
    )
)
def monitor_list_objects(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    result = call_monitor_rpc("monitor_objects", config)
    if not result.get("success"):
        return result
    summarized = _summarize_monitor_objects(result.get("data"))
    payload = wrap_success(summarized)
    payload["_next_step_hint"] = _ask_object_type_hint(summarized)
    return payload


@tool(
    description=(
        "【主机CPU使用率】第2步：按monitor_obj_id列出实例（含主机名和IP）。"
        "monitor_obj_id 只能来自第1步返回的对象 id，且须用户已明确类型或已选择；每个 obj_id 只调一次。"
        "keyword 用完整主机名/IP 或用户原词，禁止截断后按台循环，禁止猜测/递增 ID。"
        "空列表且用户未声明类型时须 request_user_choice 问对象类型；已声明类型则不要再问。"
        "后续 instance_ids 必须用本列表 instance_id，禁止用 name 或 IP 代替，禁止CMDB的inst_uuid/_id。"
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
    items = _instance_rows(result.get("data"))
    needle = str(keyword or "").strip().lower()
    matched = [item for item in items if _instance_matches_keyword(item, needle)] if needle else items
    payload = wrap_success(_summarize_monitor_instances(matched))
    if not isinstance(payload.get("data"), list):
        payload["data"] = []
    if not items:
        payload["message"] = _EMPTY_INSTANCE_OBJECT_MESSAGE
        payload["_next_step_hint"] = _EMPTY_INSTANCE_NEXT_HINT
        return payload
    if needle and not matched:
        payload["keyword"] = str(keyword).strip()
        payload["message"] = _UNMATCHED_INSTANCE_KEYWORD_MESSAGE
        payload["available_names"] = _available_instance_names(items)
        payload["_next_step_hint"] = _EMPTY_INSTANCE_NEXT_HINT
        return payload
    payload["_next_step_hint"] = _instance_query_hint(payload["data"])
    return payload
