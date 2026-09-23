from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.alerts.utils import call_alerts_rpc, wrap_error


@tool(
    description=(
        "查询统一告警中心工单列表。口语「还有没有没关的告警」「某台还在告警」「未分派」必须用本工具；"
        "主机名/IP/标题放 keyword。不要用 monitor_list_active_alerts，也不要先问监控对象类型。"
        "可按 status/level/keyword 过滤，只读。"
    )
)
def alerts_list_alerts(
    status: Optional[Any] = None,
    level: Optional[Any] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    query_data = {
        "status": status,
        "level": level,
        "keyword": keyword or "",
        "page": page,
        "page_size": page_size,
    }
    return call_alerts_rpc("list_alerts", config, query_data=query_data)


@tool(description="按 alert_id 查询告警中心告警详情，只读。")
def alerts_get_alert_detail(
    alert_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not alert_id:
        return wrap_error("alert_id is required")
    return call_alerts_rpc("get_alert_detail", config, alert_id=alert_id)


@tool(description="按 alert_id 查询告警关联事件列表，只读。")
def alerts_list_alert_events(
    alert_id: str,
    page: int = 1,
    page_size: int = 20,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not alert_id:
        return wrap_error("alert_id is required")
    return call_alerts_rpc(
        "list_alert_events",
        config,
        alert_id=alert_id,
        query_data={"page": page, "page_size": page_size},
    )
