from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, resolve_monitor_runtime_params, wrap_error


@tool(description="List latest active monitor alerts.")
def monitor_list_active_alerts(
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
    monitor_obj_id: Optional[str] = None,
    limit: int = 10,
    instance_ids: Optional[List[str]] = None,
    level: Optional[Any] = None,
    alert_type: Optional[Any] = None,
) -> Dict[str, Any]:
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "limit": limit,
        "instance_ids": instance_ids or [],
        "level": level,
        "alert_type": alert_type,
    }
    return call_monitor_rpc(
        "query_latest_active_alerts",
        **runtime_params,
        query_data=query_data,
    )


@tool(description="Query historical monitor alert segments.")
def monitor_query_alert_segments(
    monitor_obj_id: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    domain: Optional[str] = None,
    team_id: Optional[int] = None,
    config: RunnableConfig = None,
    instance_ids: Optional[List[str]] = None,
    status: Optional[Any] = None,
    level: Optional[Any] = None,
    alert_type: Optional[Any] = None,
    page: int = 1,
    page_size: int = 100,
) -> Dict[str, Any]:
    if not monitor_obj_id:
        return wrap_error("monitor_obj_id is required")
    if start in (None, ""):
        return wrap_error("start is required")
    if end in (None, ""):
        return wrap_error("end is required")
    runtime_params = resolve_monitor_runtime_params(config, username=username, password=password, domain=domain, team_id=team_id)
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "start": start,
        "end": end,
        "instance_ids": instance_ids or [],
        "status": status,
        "level": level,
        "alert_type": alert_type,
        "page": page,
        "page_size": page_size,
    }
    return call_monitor_rpc(
        "query_monitor_alert_segments",
        **runtime_params,
        query_data=query_data,
    )
