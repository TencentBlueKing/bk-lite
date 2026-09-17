from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.log.utils import call_log_rpc, wrap_error


def _resolve_log_time_range(start: Optional[str], end: Optional[str]) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
    has_start = bool(str(start or "").strip())
    has_end = bool(str(end or "").strip())
    if has_start != has_end:
        return None, wrap_error("start and end must be provided together")
    if has_start and has_end:
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


@tool(description="结构化查询日志：关键词、可选时间范围（默认近 24 小时）、可选日志分组。不要手写查询语句。")
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
    query_data = {
        "keyword": keyword or "",
        "time_range": time_range,
        "limit": limit,
        "log_group_ids": log_group_ids or [],
    }
    return call_log_rpc("search_structured", config, query_data=query_data)


@tool(description="高级日志查询：接受原生 LogsQL 查询语句。时间范围可选，默认近 24 小时。权限仍按调用方日志分组过滤。")
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
