from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.core.utils.time_util import parse_rfc3339_utc
from apps.opspilot.metis.llm.tools.log.utils import call_log_rpc, wrap_error
from apps.opspilot.metis.llm.tools.search_terms import SEARCH_NOTE, resolve_search_terms, user_message_from_config

_TIME_FORMAT_ERROR = "start 和 end 必须是带时区的 RFC3339，例如 2026-10-21T15:03:09+08:00 或 2026-10-21T07:03:09Z。不要使用 2026-10-21 15:03:09 这种没有时区的时间。"


def _resolve_log_time_range(start: Optional[str], end: Optional[str]) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
    has_start = bool(str(start or "").strip())
    has_end = bool(str(end or "").strip())
    if has_start != has_end:
        return None, wrap_error("start and end must be provided together")
    if has_start and has_end:
        try:
            parse_rfc3339_utc(str(start).strip())
            parse_rfc3339_utc(str(end).strip())
        except ValueError:
            return None, wrap_error(_TIME_FORMAT_ERROR)
        return [str(start).strip(), str(end).strip()], None
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
        "start 和 end 必须成对出现，只能是带时区的 RFC3339，例如 2026-10-21T15:03:09+08:00 或 2026-10-21T07:03:09Z。"
        "禁止使用 2026-10-21 15:03:09 这种没有时区的时间。两者都省略时默认近 24 小时。"
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
    time_range, error = _resolve_log_time_range(start, end)
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
        "高级日志查询：接受原生 LogsQL 查询语句。"
        "start 和 end 必须成对出现，只能是带时区的 RFC3339，例如 2026-10-21T15:03:09+08:00 或 2026-10-21T07:03:09Z。"
        "禁止使用没有时区的时间。两者都省略时默认近 24 小时。权限仍按调用方日志分组过滤。"
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
    time_range, error = _resolve_log_time_range(start, end)
    if error:
        return error
    query_data = {
        "query": query,
        "time_range": time_range,
        "limit": limit,
        "log_group_ids": log_group_ids or [],
    }
    return call_log_rpc("search_structured", config, query_data=query_data)
