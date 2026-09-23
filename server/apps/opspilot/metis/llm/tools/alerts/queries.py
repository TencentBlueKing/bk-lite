from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.alerts.utils import call_alerts_rpc, wrap_error
from apps.opspilot.metis.llm.tools.search_terms import SEARCH_NOTE, resolve_search_terms, user_message_from_config


@tool(description=("查询统一告警中心工单列表。服务端按用户原问生成词表（原词加固定同义词）并做或匹配，" "覆盖标题、正文、资源名和告警 ID。不要自己拼接关键字，也不要因为空结果换词重搜。" "可按 status/level 过滤，只读。"))
def alerts_list_alerts(
    status: Optional[Any] = None,
    level: Optional[Any] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    terms = resolve_search_terms(user_message_from_config(config), keyword)
    query_data = {
        "status": status,
        "level": level,
        "keywords": terms,
        "page": page,
        "page_size": page_size,
    }
    result = call_alerts_rpc("list_alerts", config, query_data=query_data)
    if isinstance(result, dict) and result.get("success"):
        result["searched_keywords"] = terms
        result["search_note"] = SEARCH_NOTE
    return result


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
