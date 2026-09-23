from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_metric_window, wrap_error, wrap_success

_METRIC_SUMMARY_KEYS = ("name", "display_name", "unit", "data_type", "metric_group")
_UNKNOWN_METRIC_HINT = (
    "metric 必须来自 monitor_list_object_metrics 返回的 name。"
    "禁止猜测 cpu.util、system.cpu.util、cpu_usage 等通用名。"
    "用户问 CPU/内存/磁盘时，先 list_object_metrics(keyword=用户词) 筛选 name/display_name 含该词的指标，再用这些 name 查时序。"
    "列表非空时不要 request_user_choice 让用户手填指标名。"
)
_EMPTY_SERIES_HINT = (
    "本次查询成功但无时序点（空矩阵/seriesMatched=0）是有效结论，不是工具失败。" "禁止改 instance_ids、IP、dimensions、start/end、step 或 metric 重试，不要换 ID 碰运气。" "直接告知用户当前窗口没有该指标数据。"
)


def _summarize_monitor_metrics(data: Any) -> list:
    if not isinstance(data, list):
        return []
    summarized = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row = {key: item[key] for key in _METRIC_SUMMARY_KEYS if key in item and item[key] not in (None, "")}
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        row["name"] = name
        summarized.append(row)
    return summarized


def _metric_matches_keyword(item: Dict[str, Any], needle: str) -> bool:
    haystack = " ".join(str(item.get(key) or "") for key in ("name", "display_name", "description", "display_description", "metric_group"))
    return needle in haystack.lower()


def _first_series_container(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    inner = data.get("data")
    if isinstance(inner, dict) and any(key in inner for key in ("result", "series", "resultType")):
        return inner
    return data


def _metric_query_is_empty(data: Any) -> bool:
    """成功查询但无时序点：空矩阵 / series=[] / seriesMatched=0。"""
    if data is None:
        return True
    if isinstance(data, list):
        return not data
    if not isinstance(data, dict):
        return False
    stats = data.get("stats")
    if isinstance(stats, dict):
        matched = stats.get("seriesMatched")
        if matched in (0, "0"):
            return True
        if isinstance(matched, str) and matched.isdigit() and int(matched) == 0:
            return True
    container = _first_series_container(data)
    if isinstance(container, list):
        return not container
    if not isinstance(container, dict):
        return False
    for key in ("result", "series"):
        value = container.get(key)
        if isinstance(value, list):
            return not value
    return False


def _filter_metrics_by_keyword(items: list, keyword: Optional[str]) -> list:
    needle = str(keyword or "").strip().lower()
    if not needle:
        return items
    return [item for item in items if _metric_matches_keyword(item, needle)]


def _metric_query_hint(items: list, keyword: Optional[str]) -> str:
    needle = str(keyword or "").strip()
    names = [str(item.get("name") or "") for item in items if item.get("name")]
    if needle and not names:
        return f"无名称/展示名包含「{needle}」的指标。禁止猜测 cpu.util 等通用名。" "可去掉 keyword 再列一次，或换用户原词；不要 request_user_choice 让用户手填指标名。"
    shown = "、".join(names[:8])
    extra = f"等共 {len(names)} 个" if len(names) > 8 else ""
    keyword_line = f"已按「{needle}」筛选。" if needle else "用户问 CPU/内存/磁盘时必须传 keyword 筛选。"
    return (
        f"{keyword_line}后续 monitor_query_metric_data 的 metric 必须用本列表 name"
        f"（{shown}{extra}），禁止猜测 cpu.util/system.cpu.util。"
        "列表非空时直接查这些 name，不要 request_user_choice 让用户手填。"
    )


@tool(description=("【主机CPU使用率】第3步：列出该对象指标定义。用户问 CPU/内存/磁盘时必须传 keyword 筛选 name/display_name。" "metric 只能用返回的 name，禁止猜测 cpu.util。与查时序同一步。"))
def monitor_list_object_metrics(
    monitor_obj_id: str,
    keyword: Optional[str] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    result = call_monitor_rpc(
        "monitor_metrics",
        config,
        monitor_obj_id=monitor_obj_id,
    )
    if not result.get("success"):
        return result
    summarized = _summarize_monitor_metrics(result.get("data"))
    filtered = _filter_metrics_by_keyword(summarized, keyword)
    payload = wrap_success(filtered)
    payload["_next_step_hint"] = _metric_query_hint(filtered, keyword)
    if str(keyword or "").strip() and summarized and not filtered:
        payload["message"] = f"无名称/展示名包含「{str(keyword).strip()}」的指标。"
    return payload


@tool(description=("【主机CPU使用率】可选：列出某实例已采集指标，确认该主机是否有CPU数据。" "参数monitor_obj_id+instance_id；可only_with_data过滤。"))
def monitor_list_instance_metrics(
    monitor_obj_id: str,
    instance_id: str,
    config: RunnableConfig = None,
    only_with_data: bool = False,
    lookback: str = "1h",
    page: int = 1,
    page_size: int = 100,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if not instance_id:
        return wrap_error("instance_id is required")
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "instance_id": instance_id,
        "only_with_data": only_with_data,
        "lookback": lookback,
        "page": page,
        "page_size": page_size,
    }
    return call_monitor_rpc(
        "monitor_instance_metrics",
        config,
        query_data=query_data,
    )


@tool(
    description=(
        "【主机CPU使用率】第4步：查询指标时序（返回CPU使用率数值）。"
        "metric 必须来自本步 monitor_list_object_metrics 返回的 name，禁止猜测 cpu.util。"
        "必填monitor_obj_id、metric；instance_ids 必须用 list_object_instances 返回的 instance_id，禁止用实例名或 IP 代替。"
        "禁止CMDB的inst_uuid/_id。可省略start/end（默认近1小时）。禁止建议top/htop/SSH。"
        "同一实例同一指标只查一次；空矩阵/无时序是有效结论，禁止改 instance_ids、IP、dimensions、时间窗或 metric 重试。"
    )
)
def monitor_query_metric_data(
    monitor_obj_id: Optional[str] = None,
    metric: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    config: RunnableConfig = None,
    step: str = "5m",
    instance_ids: Optional[List[str]] = None,
    dimensions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if not metric:
        return wrap_error("metric is required")
    try:
        start_ms, end_ms = resolve_metric_window(start, end)
    except ValueError as exc:
        return wrap_error(str(exc))
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "metric": metric,
        "start": start_ms,
        "end": end_ms,
        "step": step,
        "instance_ids": instance_ids or [],
        "dimensions": dimensions or {},
    }
    result = call_monitor_rpc(
        "query_monitor_data_by_metric",
        config,
        query_data=query_data,
    )
    error = str(result.get("error") or "")
    if not result.get("success") and "指标不存在" in error:
        result["_next_step_hint"] = _UNKNOWN_METRIC_HINT
    elif result.get("success") and _metric_query_is_empty(result.get("data")):
        result["_next_step_hint"] = _EMPTY_SERIES_HINT
    return result


@tool(description=("【主机CPU使用率】按监控 instance_ids 查询主机 CPU/内存/磁盘均值与最高值快照。" "须用监控 instance_id/主机名/IP，禁止 CMDB 的 inst_uuid/_id。"))
def monitor_get_host_resource_snapshot(
    instance_ids: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not instance_ids:
        return wrap_error("instance_ids is required")
    return call_monitor_rpc(
        "get_host_resource_snapshot",
        config,
        instance_ids=instance_ids,
    )
