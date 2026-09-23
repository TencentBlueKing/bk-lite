from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.monitor.utils import call_monitor_rpc, to_monitor_epoch_ms, wrap_error


@tool(
    description=(
        "【监控策略告警】查询监控扫描产生的主机/实例活跃告警（MonitorAlert），不是告警中心工单。"
        "仅当用户点名监控告警/策略告警/new 状态时使用；口语「没关的告警/某台还在告」应改用 alerts_list_alerts。"
        "monitor_obj_id 只能是 monitor_list_objects 返回的数字对象类型 id；"
        "instance_ids 须用监控 instance_id（含 CMDB monitor_id、1_IP_端口）、实例名或 IP，禁止把实例标识填进 monitor_obj_id，禁止 CMDB 的 inst_uuid/_id。"
    )
)
def monitor_list_active_alerts(
    config: RunnableConfig = None,
    monitor_obj_id: Optional[str] = None,
    limit: int = 10,
    instance_ids: Optional[List[str]] = None,
    level: Optional[Any] = None,
    alert_type: Optional[Any] = None,
) -> Dict[str, Any]:
    if monitor_obj_id not in (None, ""):
        obj_id = str(monitor_obj_id).strip()
        if not obj_id.isdigit():
            return wrap_error(
                "monitor_obj_id 必须是监控对象类型的数字 id（来自 monitor_list_objects 的 id）；"
                "CMDB 返回的 monitor_id、实例名、IP 或形如 1_IP_端口 的标识请放 instance_ids，不要填 monitor_obj_id。"
            )
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
    try:
        start_ms = to_monitor_epoch_ms(start)
        end_ms = to_monitor_epoch_ms(end)
    except ValueError as exc:
        return wrap_error(str(exc))
    query_data = {
        "monitor_obj_id": monitor_obj_id,
        "start": start_ms,
        "end": end_ms,
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
