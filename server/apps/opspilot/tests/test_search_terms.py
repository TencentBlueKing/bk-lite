"""问句词表：原词加固定同义词，不把两个概念粘成一个短语。"""

from langchain_core.messages import ToolMessage

from apps.opspilot.metis.llm.middleware.tool_runtime import repeated_or_search_denial
from apps.opspilot.metis.llm.tools.search_terms import build_search_terms, resolve_search_terms


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
