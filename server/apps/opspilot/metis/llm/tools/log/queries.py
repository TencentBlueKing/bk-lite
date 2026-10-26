from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.utils.time_util import format_rfc3339_utc
from apps.opspilot.metis.llm.tools.log.utils import call_log_rpc, wrap_error
from apps.opspilot.metis.llm.tools.search_terms import SEARCH_NOTE, resolve_search_terms, user_message_from_config
from apps.opspilot.metis.llm.tools.user_clock import parse_user_wall_time, timezone_name_from_config

_TIME_FORMAT_ERROR = "start 和 end 要是时间，例如 2026-10-22 14:28:00 或 2026-10-22T06:28:00Z。没写时区时按当前用户时区理解。"


def _resolve_log_time_range(
    start: Optional[str],
    end: Optional[str],
    tz_name: str | None = None,
) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
    has_start = bool(str(start or "").strip())
    has_end = bool(str(end or "").strip())
    if has_start != has_end:
        return None, wrap_error("start and end must be provided together")
    if has_start and has_end:
        try:
            start_at = parse_user_wall_time(start, tz_name)
            end_at = parse_user_wall_time(end, tz_name)
        except ValueError:
            return None, wrap_error(_TIME_FORMAT_ERROR)
        return [format_rfc3339_utc(start_at), format_rfc3339_utc(end_at)], None
    now = datetime.now(timezone.utc)
    end_s = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    start_s = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return [start_s, end_s], None


@tool(description="列出当前用户可访问的日志分组，后续查询可按分组收窄。")
def log_list_groups(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    return call_log_rpc("list_log_groups", config)


@tool(
    description=(
        "结构化查询日志。服务端按用户原问生成词表并在 message 上做或匹配。"
        "start 和 end 必须成对出现。没写时区时按当前用户时区理解，例如 2026-10-22 14:28:00；"
        "写了 Z 或 ±HH:MM 则按该偏移。两者都省略时默认近 24 小时。"
        "可选日志分组。不要自己拼接关键字，不要手写查询语句，也不要因为空结果换词重搜。"
        "参数错误是调用失败，不是没有日志；按错误改正后再查。成功且结果为空才是没有命中。"
    )
)
def log_search_structured(
    keyword: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    log_group_ids: Optional[List[str]] = None,
    limit: int = 10,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    time_range, error = _resolve_log_time_range(start, end, timezone_name_from_config(config))
    if error:
        return error
    terms = resolve_search_terms(user_message_from_config(config), keyword)
    query_data = {
        "keywords": terms,
        "time_range": time_range,
        "limit": limit,
        "log_group_ids": log_group_ids or [],
    }
    result = call_log_rpc("search_structured", config, query_data=query_data)
    if isinstance(result, dict) and result.get("success"):
        result["searched_keywords"] = terms
        result["search_note"] = SEARCH_NOTE
    return result


@tool(
    description=(
        "高级日志查询：接受原生 LogsQL 查询语句。" "start 和 end 必须成对出现。没写时区时按当前用户时区理解，例如 2026-10-22 14:28:00；" "写了 Z 或 ±HH:MM 则按该偏移。两者都省略时默认近 24 小时。权限仍按调用方日志分组过滤。"
    )
)
def log_search_raw(
    query: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 10,
    log_group_ids: Optional[List[str]] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not query:
        return wrap_error("query is required")
    time_range, error = _resolve_log_time_range(start, end, timezone_name_from_config(config))
    if error:
        return error
    query_data = {
        "query": query,
        "time_range": time_range,
        "limit": limit,
        "log_group_ids": log_group_ids or [],
    }
    return call_log_rpc("search_structured", config, query_data=query_data)
