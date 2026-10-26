import re
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.utils.time_util import format_rfc3339_utc
from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_metric_window, wrap_error, wrap_success
from apps.opspilot.metis.llm.tools.search_terms import user_message_from_config
from apps.opspilot.metis.llm.tools.user_clock import parse_user_wall_time, timezone_name_from_config

_METRIC_SUMMARY_KEYS = ("name", "display_name", "unit", "data_type", "metric_group")
_METRIC_NAME_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_UNKNOWN_METRIC_HINT = (
    "metric 必须来自 monitor_list_object_metrics 返回的 name。"
    "禁止使用目录里没有的指标名。"
    "先 list_object_metrics，keyword 用用户原文里的指标名或指标说法，筛选 name/display_name。"
    "用户原文已经写出指标名时，keyword 用该指标名，不要改成类别词。"
    "不要 request_user_choice 让用户手填指标名；只命中一个就直接查，没命中或命中多个再让用户选。"
)
_EMPTY_SERIES_HINT = (
    "本次查询成功但无时序点（空矩阵/seriesMatched=0）是有效结论，不是参数错误。" "空值表示当前窗口没有数据，禁止写成参数无效，禁止让用户检查时间范围、step、instance_ids、dimensions。" "禁止改这些参数重试。直接告知用户当前窗口没有该指标数据。"
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


def _metrics_named_in_text(items: list, text: str) -> list:
    """用户原文里与目录 name 完全相同的标识符优先，不看模型另传的类别词。"""
    tokens = {token.lower() for token in _METRIC_NAME_TOKEN.findall(str(text or ""))}
    if not tokens:
        return []
    matched = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        key = name.lower()
        if not name or key not in tokens or key in seen:
            continue
        seen.add(key)
        matched.append(item)
    return matched


def _metric_choice_label(item: Dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    display = str(item.get("display_name") or "").strip()
    if display and display != name:
        return f"{display} ({name})"
    return name


def _metric_choice_options(items: list) -> list:
    options = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        options.append(_metric_choice_label(item))
    return options


def _metric_query_hint(items: list, keyword: Optional[str], catalog: Optional[list] = None) -> str:
    needle = str(keyword or "").strip()
    names = [str(item.get("name") or "") for item in items if item.get("name")]
    if not needle:
        return "必须传 keyword：用户原文里的指标名，或用户用来指这个指标的说法。禁止使用目录里没有的指标名。"
    if not names:
        if not catalog:
            return f"无名称/展示名包含「{needle}」的指标，该对象也没有指标定义。不要换 keyword 再试。"
        return (
            f"无名称/展示名包含「{needle}」的指标。立刻 request_user_choice（question_type=single_select），options 原样使用本结果 choices。"
            "不要逐个试指标。可以换 keyword 再查。"
            "用户选定后，monitor_query_metric_data 的 metric 用括号里的 name。禁止使用目录里没有的指标名。"
        )
    if len(names) == 1:
        return f"只命中 {names[0]}。直接用这个 name 查时序，不要 request_user_choice，也不要再列指标。禁止使用目录里没有的指标名。"
    if len(names) > 1:
        return (
            f"已按「{needle}」命中 {len(_metric_choice_options(items))} 个指标。不要逐个查询。"
            "立刻 request_user_choice（question_type=single_select），options 原样使用本结果 choices。"
            "用户选定后只用对应 name 查一次时序。禁止使用目录里没有的指标名。"
        )
    return "必须传 keyword：用户原文里的指标名，或用户用来指这个指标的说法。禁止使用目录里没有的指标名。"


@tool(
    description=(
        "列出该对象指标定义。keyword 用用户原文里的指标名或指标说法，筛选 name/display_name。"
        "用户原文已经写出指标名时传该指标名，不要改成类别词。"
        "只命中一个 name 时直接用它查时序。"
        "没命中或命中多个时调用 request_user_choice，options 用返回的 choices，让用户选指标。"
        "可以换 keyword 再查，但不要逐个试指标。"
        "禁止使用目录里没有的指标名。"
    )
)
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
    named = _metrics_named_in_text(summarized, user_message_from_config(config))
    filtered = named or _filter_metrics_by_keyword(summarized, keyword)
    payload = wrap_success(filtered)
    needle = str(keyword or "").strip()
    ask_user = bool(needle or named) and (not filtered or len(_metric_choice_options(filtered)) > 1)
    if ask_user:
        payload["choices"] = _metric_choice_options(summarized if not filtered else filtered)
    hint_keyword = keyword
    if not needle and named:
        hint_keyword = " ".join(str(item.get("name") or "") for item in named)
    payload["_next_step_hint"] = _metric_query_hint(filtered, hint_keyword, summarized)
    if needle and summarized and not filtered:
        payload["message"] = f"无名称/展示名包含「{needle}」的指标。请让用户从 choices 里选择。可以换 keyword，不要逐个试指标。"
    return payload


@tool(description=("可选：列出某实例已采集指标，确认该实例是否有目标指标数据。" "参数 monitor_obj_id+instance_id；可 only_with_data 过滤。"))
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
        "查询该对象已纳管的任意指标时序。"
        "metric 必须来自本步 monitor_list_object_metrics 返回的 name，禁止使用目录里没有的指标名。"
        "必填 monitor_obj_id、metric；instance_ids 只能原样复制 monitor_list_object_instances 返回记录的 instance_id 字段。"
        "禁止用 name、IP、id、cmdb_id，禁止用 CMDB 的 inst_id、inst_uuid、_id，禁止传负数，列表里没有的值不要编造。"
        "可省略 start/end（默认近1小时）。没写时区的时间按当前用户时区理解，不要当成 UTC；写了 Z 或 ±HH:MM 则按该偏移。"
        "禁止建议 top/htop/SSH。"
        "同一实例同一指标只查一次。空矩阵、无时序、空值是查询成功但没有数据，不是参数错误；"
        "禁止把空值写成参数无效，禁止让用户检查时间范围、step、instance_ids、dimensions，也禁止因此重试。"
        "只有缺参或类型不对才是参数错误。有数值就按数值回答。"
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
        start_ms, end_ms = resolve_metric_window(start, end, tz_name=timezone_name_from_config(config))
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
    elif result.get("success"):
        skipped = (result.get("data") or {}).get("skipped_instance_ids") if isinstance(result.get("data"), dict) else None
        if skipped:
            result["_next_step_hint"] = "部分实例无法识别或无权限，已跳过并写在 skipped_instance_ids。其余实例的时序仍在结果里，不要逐个重试被跳过的实例。"
    return result


@tool(
    description=(
        "根据最近一段时间的监控历史，估算每条序列的当前值、每天变化量，以及还有几天到阈值。"
        "没到阈值的序列也会返回，within_horizon 为 true 才是预测跨度内会到达阈值。"
        "用户问未来会不会写满、超阈值或要出预测报告时用本工具，不要再用原始时序心算。"
        "metric 必须来自 monitor_list_object_metrics 返回的 name。"
        "instance_ids 省略或空列表表示该对象下全部已授权实例。"
        "lookback_days 默认 14，horizon_days 默认 7，threshold 默认 100。"
    )
)
def monitor_summarize_metric_trend(
    monitor_obj_id: Optional[str] = None,
    metric: Optional[str] = None,
    lookback_days: float = 14,
    horizon_days: float = 7,
    threshold: float = 100,
    instance_ids: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if not metric:
        return wrap_error("metric is required")
    return call_monitor_rpc(
        "summarize_metric_trend",
        config,
        query_data={
            "monitor_obj_id": monitor_obj_id,
            "metric": metric,
            "lookback_days": lookback_days,
            "horizon_days": horizon_days,
            "threshold": threshold,
            "instance_ids": instance_ids or [],
        },
    )


@tool(description=("按监控 instance_ids 查询主机 CPU/内存/磁盘均值与最高值快照。" "须用监控 instance_id/主机名/IP，禁止 CMDB 的 inst_uuid/_id。"))
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


@tool(
    description=(
        "按时间窗对全量主机做 CPU/内存/磁盘监控指标使用率排行（Top N）。"
        "用户问「最近/近 N 分钟使用率最高的前 M 台主机」「哪些主机磁盘高」等排名类问题时必须用本工具，"
        "不要用 monitor_get_host_resource_snapshot（它只出全局聚合快照值、不排名、不接受时间窗），"
        "也不要逐台传 instance_ids 调 query_metric_data 再手工排序。"
        "metric_type 取 cpu/memory/disk；窗口用 lookback_minutes（如「最近5分钟」传 5），"
        "或 time 传起止时间。没写时区的时间按当前用户时区理解，不要当成 UTC；写了 Z 或 ±HH:MM 则按该偏移。"
        "limit 默认 10。"
        "aggregation=max 看窗口内峰值（默认，瞬时打满），avg 看持续偏高；返回行同时含 peak_percent 与 avg_percent。"
    )
)
def monitor_get_host_resource_top_by_time(
    metric_type: str = "disk",
    lookback_minutes: Optional[float] = None,
    time: Optional[List[str]] = None,
    aggregation: str = "max",
    limit: int = 10,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not metric_type:
        return wrap_error("metric_type is required")
    if lookback_minutes in (None, "") and not time:
        return wrap_error("lookback_minutes 或 time is required")
    resolved_time = time
    if time:
        if not isinstance(time, (list, tuple)):
            return wrap_error("time 必须是起止两个时间")
        try:
            tz_name = timezone_name_from_config(config)
            resolved_time = [format_rfc3339_utc(parse_user_wall_time(item, tz_name)) for item in time]
        except ValueError as exc:
            return wrap_error(str(exc))
    return call_monitor_rpc(
        "get_host_resource_top_by_time",
        config,
        metric_type=metric_type,
        lookback_minutes=lookback_minutes,
        time=resolved_time,
        aggregation=aggregation,
        limit=limit,
    )
