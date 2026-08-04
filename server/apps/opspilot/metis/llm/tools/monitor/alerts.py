from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, wrap_error


@tool(description=("【主机告警】查询BK-Lite当前活跃告警。" "可按monitor_obj_id/instance_ids/级别过滤；排查主机告警用此工具。"))
def monitor_list_active_alerts(
    config: RunnableConfig = None,
    monitor_obj_id: Optional[str] = None,
    limit: int = 10,
    instance_ids: Optional[List[str]] = None,
    level: Optional[Any] = None,
    alert_type: Optional[Any] = None,
) -> Dict[str, Any]:
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "limit": limit,
        "instance_ids": instance_ids or [],
        "level": level,
        "alert_type": alert_type,
    }
    return call_monitor_rpc(
        "query_latest_active_alerts",
        config,
        query_data=query_data,
    )


@tool(description=("【主机告警历史】按时间窗查询告警片段。" "必填monitor_obj_id、start、end；可筛实例/状态/级别。"))
def monitor_query_alert_segments(
    monitor_obj_id: Optional[str] = None,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
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
        config,
        query_data=query_data,
    )
