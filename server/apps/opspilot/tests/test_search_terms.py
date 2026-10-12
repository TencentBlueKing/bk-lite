"""问句词表：原词加固定同义词，不把两个概念粘成一个短语。"""

from langchain_core.messages import ToolMessage

from apps.opspilot.metis.llm.middleware.tool_runtime import repeated_or_search_denial, terminal_success_denial
from apps.opspilot.metis.llm.tools.search_terms import build_search_terms, resolve_search_terms, user_message_from_config, user_question_for_search


def test_mall_question_splits_shop_and_gateway_refusal():
    terms = build_search_terms("商城页面最近特别慢，告警中心和日志两边对一下前端报错还是网关在拒绝")
    assert "商城" in terms
    assert "前端" in terms
    assert "网关" in terms
    assert "报错" in terms
    assert "connection refused" in terms
    assert "502" in terms
    assert "upstream" in terms
    assert "商城 502" not in terms


def test_order_timeout_keeps_interface_name_and_timeout_synonyms():
    terms = build_search_terms("下单接口超时了，告警和对应日志两边有没有 timeout")
    assert "下单接口" in terms
    assert "timeout" in terms
    assert "timed out" in terms
    assert "下单超时" not in terms


def test_resolve_ignores_glued_model_keyword_when_user_text_exists():
    terms = resolve_search_terms("下单接口超时了，有没有 timeout", "下单超时")
    assert "下单接口" in terms
    assert "下单超时" not in terms


def test_resolve_splits_model_keyword_when_user_text_missing():
    assert resolve_search_terms("", "商城 502") == ["商城", "502"]


def test_error_log_question_keeps_ascii_keyword():
    terms = build_search_terms("查询最近24小时的error日志")
    assert "error" in terms
    assert "快照" not in terms
    assert "检索" not in terms


def test_page_context_injection_does_not_pollute_search_terms():
    """页面快照导语/DOM 文案不得盖住用户原问里的 error。"""
    injected = (
        "以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。"
        "时间范围、横轴起止与 KPI 一律以 <current_page> 本轮快照为准，"
        "若缺少查询对象、对象类型、时间范围或要看的指标/告警类型，必须调用 request_user_choice。\n\n"
        "查询最近24小时的error日志\n\n"
        "<current_page>\n"
        "url: /log/search\n"
        "app: log\n"
        "title: 日志搜索\n"
        "## 字段\n"
        "检索\n"
        "快照\n"
        "以下是同当前当前\n"
        "</current_page>"
    )
    assert user_question_for_search(injected) == "查询最近24小时的error日志"
    terms = resolve_search_terms(injected, "error")
    assert "error" in terms
    assert "快照" not in terms
    assert "检索" not in terms
    assert "以下是同当前当前" not in terms


def test_focused_page_context_extracts_quoted_question():
    injected = "本轮用户问题是「查询最近24小时的error日志」，已定位到图表《查询直方图》。" "只根据本轮 <current_page> 中的截图与文字回答这一问。\n\n" "<current_page>\n## KPI 快照\n检索\n</current_page>"
    assert user_question_for_search(injected) == "查询最近24小时的error日志"
    assert "error" in resolve_search_terms(injected, "error")


def test_user_message_from_config_strips_page_context():
    injected = "以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。\n\n" "查询最近24小时的error日志\n\n" "<current_page>\n快照\n检索\n</current_page>"
    config = {"configurable": {"user_message": injected}}
    assert user_message_from_config(config) == "查询最近24小时的error日志"


def test_second_log_search_is_denied_after_success():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "log_search_structured", "args": {"keyword": "connection refused"}},
            "messages": [
                ToolMessage(content='{"success": true, "data": []}', tool_call_id="call-1", name="log_search_structured"),
            ],
        },
    )()
    denied = repeated_or_search_denial(request)
    assert denied is not None
    assert "不要换关键字" in denied.content


def test_terminal_hint_stops_another_call_even_when_args_change():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "prepare_dashboard_proposal", "args": {"proposal": {"schemaVersion": "1.0"}}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "_next_step_hint": "方案已校验通过。不要再次调用 prepare_dashboard_proposal。"}',
                    tool_call_id="call-1",
                    name="prepare_dashboard_proposal",
                ),
            ],
        },
    )()
    denied = terminal_success_denial(request)
    assert denied is not None
    assert "不要再调用" in denied.content

    retry = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "prepare_dashboard_proposal", "args": {"proposal": {"schemaVersion": "1.0"}}},
            "messages": [
                ToolMessage(
                    content='{"success": true, "_next_step_hint": "按这个结构改完再调用一次，不要原样重试。"}',
                    tool_call_id="call-1",
                    name="prepare_dashboard_proposal",
                ),
            ],
        },
    )()
    assert terminal_success_denial(retry) is None
