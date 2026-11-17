import json
from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.alerts.utils import call_alerts_rpc, wrap_error
from apps.opspilot.metis.llm.tools.search_terms import SEARCH_NOTE, resolve_search_terms, user_message_from_config

_ALERT_PAGE_SIZE = 100
_ALERT_MAX_RECORDS = 1000
_ALERT_MAX_PAGES = 10
_ALERT_MAX_BYTES = 1024 * 1024


def _incomplete_alert_query(reason: str, retrieved_count: int = 0, pages_fetched: int = 0) -> Dict[str, Any]:
    return {
        "success": False,
        "complete": False,
        "error": reason,
        "retrieved_count": retrieved_count,
        "pages_fetched": pages_fetched,
    }


def _fetch_complete_alerts(config: Optional[RunnableConfig], query_data: Dict[str, Any]) -> Dict[str, Any]:
    rows = []
    seen_ids = set()
    expected_count = None
    row_bytes = 0
    for page in range(1, _ALERT_MAX_PAGES + 1):
        result = call_alerts_rpc("list_alerts", config, query_data={**query_data, "page": page, "page_size": _ALERT_PAGE_SIZE})
        if not isinstance(result, dict) or not result.get("success"):
            reason = result.get("error", "alerts query failed") if isinstance(result, dict) else "invalid alerts response"
            return _incomplete_alert_query(reason, len(rows), page - 1)
        data = result.get("data")
        if not isinstance(data, dict):
            return _incomplete_alert_query("invalid alerts page", len(rows), page - 1)
        count, items = data.get("count"), data.get("items")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or not isinstance(items, list):
            return _incomplete_alert_query("invalid alerts page", len(rows), page - 1)
        if data.get("page") != page or data.get("page_size") != _ALERT_PAGE_SIZE or len(items) > _ALERT_PAGE_SIZE:
            return _incomplete_alert_query("invalid alerts page", len(rows), page - 1)
        if count > _ALERT_MAX_RECORDS:
            return _incomplete_alert_query("alerts record limit exceeded; narrow query scope before analysis", len(rows), page - 1)
        if expected_count is not None and count != expected_count:
            return _incomplete_alert_query("alerts count changed during pagination; result is incomplete", len(rows), page - 1)
        expected_count = count
        if len(items) != min(_ALERT_PAGE_SIZE, count - len(rows)):
            return _incomplete_alert_query("alerts pagination made incomplete progress", len(rows), page - 1)
        for item in items:
            alert_id = item.get("alert_id") if isinstance(item, dict) else None
            if not isinstance(alert_id, str) or not alert_id:
                return _incomplete_alert_query("invalid alert_id in page", len(rows), page - 1)
            if alert_id in seen_ids:
                return _incomplete_alert_query("duplicate alert_id across pages; result is incomplete", len(rows), page - 1)
            seen_ids.add(alert_id)
        row_bytes += len(json.dumps(items, ensure_ascii=False).encode("utf-8"))
        if row_bytes > _ALERT_MAX_BYTES:
            return _incomplete_alert_query("alerts byte limit exceeded; narrow query scope before analysis", len(rows), page - 1)
        rows.extend(items)
        if len(rows) == count:
            return {
                "success": True,
                "data": {
                    "count": count,
                    "items": rows,
                    "complete": True,
                    "retrieved_count": len(rows),
                    "pages_fetched": page,
                },
            }
    return _incomplete_alert_query("alerts page limit exceeded; result is incomplete", len(rows), _ALERT_MAX_PAGES)


@tool(
    description=(
        "查询统一告警中心工单列表。默认fetch_all=true自动从第一页取齐，固定100条/页，上限1000条、10页、1MiB。"
        "做总体统计或按对象、指标、阈值分析必须使用完整模式；只有complete=true才可分析完整结果。"
        "大结果落盘时必须读取完整JSON；可用python_execute_direct时，用json.load(open('large_tool_results/<文件名>'))，"
        "校验len(result['data']['items'])==result['data']['count']后聚合。禁止仅分析预览、以grep行数代替记录数或缩小page_size绕过预览。"
        "失败、超限或数据变动时不会返回部分明细；应说明未取全或缩小查询范围，不得擅自改成抽样分析。"
        "仅明确需要单页时传fetch_all=false并使用page/page_size；单页complete=false不代表完整数据。"
        "完整模式page必须为1，page_size由工具固定为100；完整只表示本次分页取得全部记录，不是同一时刻快照。"
        "口语「没关的告警/未分派/当前有哪些告警」用本工具。"
        "查某台主机是否还在告时：本工具查告警中心工单；监控详情页「告警列表」还须用 "
        "monitor_list_active_alerts（监控策略告警未必进告警中心），两套都要查。"
        "status=active 表示未关闭的活动告警（pending、processing、unassigned），与告警中心活动页一致；"
        "不传 status 则包含已关闭。具体状态用 pending、processing、unassigned、closed、resolved、auto_close、auto_recovery。"
        "「当前」「有哪些」这类口头语不会当关键字。问有哪些告警时不要传 keyword。"
        "关键字只取正文内容，并做或匹配，覆盖标题、正文、资源名和告警 ID。"
        "中文正文必须用 keyword 传入，并且这个词要原样出现在用户原话里。状态、时间和查询口头语不要传，中英文都一样。"
        "问句里的普通英文单词和输出格式不会变成关键字。error、主机名、IP、指标名可以。"
        "服务端不会从整句里再拆中文关键字。不要因为空结果换词重搜。可按 status/level 过滤，只读。"
    )
)
def alerts_list_alerts(
    status: Optional[Any] = None,
    level: Optional[Any] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    fetch_all: bool = True,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if fetch_all and page != 1:
        return _incomplete_alert_query("fetch_all requires page=1")
    terms = resolve_search_terms(user_message_from_config(config), keyword)
    query_data = {
        "status": status,
        "level": level,
        "keywords": terms,
        "page": page,
        "page_size": page_size,
    }
    if fetch_all:
        result = _fetch_complete_alerts(config, query_data)
    else:
        result = call_alerts_rpc("list_alerts", config, query_data=query_data)
        if isinstance(result, dict) and result.get("success"):
            data = result["data"]
            count, items = data["count"], data["items"]
            current_page, size = data["page"], data["page_size"]
            data["complete"] = current_page == 1 and len(items) == count
            data["next_page"] = current_page + 1 if (current_page - 1) * size + len(items) < count else None
    if isinstance(result, dict) and result.get("success") and terms:
        result["searched_keywords"] = terms
        result["search_note"] = SEARCH_NOTE
    if fetch_all and result.get("success") and len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > _ALERT_MAX_BYTES:
        return _incomplete_alert_query(
            "alerts byte limit exceeded; narrow query scope before analysis",
            result["data"]["retrieved_count"],
            result["data"]["pages_fetched"],
        )
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
