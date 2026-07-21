"""strip_phantom_tool_calls 单元测试 + 跨 chunk buffer 集成测试。

锁定行为:
- 单 chunk 内完整 phantom call 一定抹掉
- 跨 chunk 拆分(没有完整闭合配对)的 phantom call 也能抹掉(buffer 机制)
- 不影响:正常文字、合法 HTML、孤立 <tool_call> 标签
- 不抛异常,空串/None 安全
"""
from __future__ import annotations

import json
import sys
from unittest.mock import patch, MagicMock

import pytest

from apps.opspilot.metis.llm.chain.report_renderers import (
    strip_phantom_tool_calls,
)
from apps.opspilot.metis.llm.chain import k8s_report_tools


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 纯函数级 strip 测试
# ---------------------------------------------------------------------------

def test_strip_removes_standard_phantom_call():
    """<tool_call>call:name{args}</tool_call> 这种典型模式必须抹掉。"""
    text = (
        "已调用 3 个工具 k8s 实时状态详情\n"
        "<tool_call>call:kubectl_get_all_resources{namespace:\"production\"}</tool_call>\n"
        "<tool_call>call:kubectl_get_all_resources{namespace:\"dev\"}</tool_call>\n"
        "现在给结论"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert "<tool_call>" not in cleaned
    assert "kubectl_get_all_resources" not in cleaned
    assert "已调用 3 个工具" in cleaned
    assert "现在给结论" in cleaned


def test_strip_removes_pipe_separated_phantom_call():
    """<|tool_call|>name(args)<|tool_call|> 这种带 pipe 的模式也抹掉。"""
    text = (
        "分析结果如下:\n"
        "<|tool_call|>call:execute{name=\"foo\"}<|tool_call|>\n"
        "继续\n"
        "<|tool_call|>call:execute{name=\"bar\"}<|tool_call|>\n"
        "完毕"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert "<|tool_call|>" not in cleaned
    assert "execute" not in cleaned
    assert "分析结果如下" in cleaned
    assert "完毕" in cleaned


def test_strip_removes_leading_pipe_phantom_call_from_screenshot():
    """模型也会输出只有左侧 pipe 的 <|tool_call> 变体。"""
    text = '<|tool_call>call:analyze_deployment_configurations{namespace:<|">default<|">}<|tool_call>'
    cleaned = strip_phantom_tool_calls(text)
    assert cleaned == ""


def test_strip_handles_multi_line_content():
    """phantom call 里 args 含换行也得能整段抹掉(re.DOTALL)。"""
    text = (
        "before\n"
        "<tool_call>call:foo{\n"
        "  multi: 'line',\n"
        "  other: 'value'\n"
        "}</tool_call>\n"
        "after"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert "before" in cleaned
    assert "after" in cleaned
    assert "multi" not in cleaned
    assert "<tool_call>" not in cleaned


def test_strip_preserves_legitimate_html():
    """普通 HTML / markdown 不应被 strip。"""
    text = (
        "<h1>报告标题</h1>\n"
        "<p>这是普通段落,带 <strong>加粗</strong> 和 <em>斜体</em></p>\n"
        "<ul><li>项 1</li><li>项 2</li></ul>\n"
        "代码片段:<tool_call> 这种不算工具调用</tool_call> 不,该 strip 掉"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert "<h1>报告标题</h1>" in cleaned
    assert "<strong>加粗</strong>" in cleaned
    assert "<em>斜体</em>" in cleaned
    assert "<ul>" in cleaned
    assert "<tool_call>这种不算" not in cleaned
    assert "</tool_call> 不" not in cleaned


def test_strip_preserves_normal_tool_call_style_text():
    """LLM 写说明文字时提到 'tool_call' 单词不应被误伤。"""
    text = (
        "我会使用 tool_call 来调用工具\n"
        "这个 tool 调用的参数是 foo\n"
        "实际是 tool_calls.json 里的字段"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert cleaned == text


def test_strip_handles_empty_string():
    assert strip_phantom_tool_calls("") == ""


def test_strip_handles_none():
    """None 安全(虽然类型注解是 str,LLM 偶尔会传 None)。"""
    assert strip_phantom_tool_calls(None) is None


def test_strip_handles_text_without_phantom_calls():
    text = "这是一段正常的 LLM 回复,没有任何工具调用。\n第二行。"
    assert strip_phantom_tool_calls(text) == text


def test_strip_handles_mixed_format():
    text = (
        "<tool_call>call:foo{args:1}</tool_call>"
        "中间普通文字"
        "<|tool_call|>call:bar{args:2}<|tool_call|>"
    )
    cleaned = strip_phantom_tool_calls(text)
    assert "<tool_call>" not in cleaned
    assert "<|tool_call|>" not in cleaned
    assert "中间普通文字" in cleaned


def test_strip_handles_malformed_close_tag_omitting_slash():
    """LLM 偶尔不写 close tag 里的 /,open 和 close 都是 <tool_call>。

    用户截图 15 实际就是这个模式:`<tool_call>call:analyze_deployment_configurations{namespace:["production"]}<tool_call>`
    之前的 regex 只匹 <tool_call>(有 /)会漏掉这种情况。手动 strip 必须 fallback 到
    "找下一次同 tag 当 close"。
    """
    text = '<tool_call>call:analyze_deployment_configurations{namespace:["production"]}<tool_call>'
    cleaned = strip_phantom_tool_calls(text)
    assert "<tool_call>" not in cleaned
    assert "analyze_deployment" not in cleaned
    assert cleaned == ""



def test_strip_handles_nested_phantom_calls():
    text = "<tool_call>outer<tool_call>inner</tool_call></tool_call>"
    cleaned = strip_phantom_tool_calls(text)
    assert "<tool_call>" not in cleaned


def test_strip_preserves_orphan_phantom_opener():
    """<tool_call> 不带闭合的孤儿标签不抹掉(避免误伤普通 <tool>...<tool> 标签)。"""
    text = "前面<tool_call> 这标签没闭合,后面跟着正常文字"
    cleaned = strip_phantom_tool_calls(text)
    assert "<tool_call> 这标签没闭合" in cleaned


# ---------------------------------------------------------------------------
# shim re-export
# ---------------------------------------------------------------------------

def test_shim_re_exports_strip_phantom_tool_calls():
    """k8s_report_tools 兼容 shim 也必须 re-export 这个新函数。"""
    assert k8s_report_tools.strip_phantom_tool_calls is strip_phantom_tool_calls


# ---------------------------------------------------------------------------
# 跨 chunk buffer 集成测试(graph.py emit 路径)
# ---------------------------------------------------------------------------

def _make_basic_graph():
    """构造一个 BasicGraph 的最小 concrete 子类实例,绕开 __init__ 和抽象方法。"""
    from apps.opspilot.metis.llm.chain.graph import BasicGraph

    class _StubGraph(BasicGraph):
        async def compile_graph(self, request):
            return None

    # __new__ 绕开 __init__,只挂方法
    return _StubGraph.__new__(_StubGraph)


def _extract_text_deltas(events):
    """从 emit 的 SSE 字符串列表里抽出所有 TEXT_MESSAGE_CONTENT 的 delta。"""
    deltas = []
    for ev in events:
        if "data: " in ev:
            try:
                payload = json.loads(ev.split("data: ", 1)[1])
                if payload.get("type") == "TEXT_MESSAGE_CONTENT":
                    deltas.append(payload.get("delta", ""))
            except Exception:
                pass
    return deltas


def _chunk_with_content(text):
    """构造一个 chunk,content 是 text,其他属性 stub。"""
    chunk = MagicMock()
    chunk.content = text
    chunk.additional_kwargs = {}
    return chunk


def test_cross_chunk_phantom_call_strip_via_buffer():
    """LLM 把 <tool_call>name{ar | gs}</tool_call> 拆 2 个 chunk 时,buffer 拼回去再 strip。"""
    from ag_ui.encoder import EventEncoder

    graph = _make_basic_graph()
    encoder = EventEncoder()
    buffers: dict = {}

    # chunk 1: <tool_call>call:analyze_deployment_   (没闭合)
    # chunk 2: configurations{namespace:["production"]}</tool_call>  (闭合)
    # 期望:拼起来 strip 后 emit 空,buffer 也清空

    # chunk 1
    events1, mid, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content('<tool_call>call:analyze_deployment_'),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=False,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    # 末尾是不闭合 phantom call,全 hold 在 buffer 不 emit(message_started=False 时直接 return)
    assert _extract_text_deltas(events1) == [], "末尾未闭合 phantom 应全 hold,不 emit"
    assert "msg-1" in buffers
    assert "<tool_call>" in buffers["msg-1"]

    # chunk 2
    events2, _, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content('configurations{namespace:["production"]}</tool_call>'),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=True,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    # 拼起来完整 phantom call,strip 后 emit 空(phantom 被抹),buffer 清空
    deltas2 = _extract_text_deltas(events2)
    full_emitted = "".join(deltas2)
    assert "<tool_call>" not in full_emitted
    assert "analyze_deployment" not in full_emitted
    assert "msg-1" not in buffers, "buffer 应该在完整 strip 后清空"


def test_cross_chunk_leading_pipe_phantom_call_strip_via_buffer():
    """截图中的 <|tool_call> 变体跨 chunk 时也不能提前泄漏到正文。"""
    from ag_ui.encoder import EventEncoder

    graph = _make_basic_graph()
    encoder = EventEncoder()
    buffers: dict = {}

    events1, _, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content("<|tool_call>call:analyze_deployment_"),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=False,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    assert _extract_text_deltas(events1) == []
    assert buffers["msg-1"].startswith("<|tool_call>")

    events2, _, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content('configurations{namespace:<|">default<|">}<|tool_call>'),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=True,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    full_emitted = "".join(_extract_text_deltas(events2))
    assert "<|tool_call>" not in full_emitted
    assert "analyze_deployment" not in full_emitted
    assert "msg-1" not in buffers


def test_single_chunk_phantom_call_still_works_with_buffer():
    """buffer 机制不能破坏单 chunk 内完整 phantom call 的 strip。"""
    from ag_ui.encoder import EventEncoder

    graph = _make_basic_graph()
    encoder = EventEncoder()
    buffers: dict = {}

    full_phantom = '<tool_call>call:analyze_deployment_configurations{namespace:["production"]}</tool_call>'
    events, _, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content(full_phantom),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=False,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    deltas = _extract_text_deltas(events)
    full = "".join(deltas)
    assert "<tool_call>" not in full, f"单 chunk phantom 必须 strip 掉,实际 emit: {full!r}"


def test_normal_text_emit_unaffected_by_buffer():
    """buffer 不能让正常 LLM 文字延迟 emit 或丢失。"""
    from ag_ui.encoder import EventEncoder

    graph = _make_basic_graph()
    encoder = EventEncoder()
    buffers: dict = {}

    # 用户截图里的实际场景:LMM 输出 5 个真实工具调用 + 1 个 phantom
    # 这里模拟"正常文字在前,phantom 在中,正常文字在后"
    text = "我会先扫全部 namespace,然后看看结果\n<tool_call>call:foo{ns:1}</tool_call>\n最终结论"
    events, _, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content(text),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-1",
        message_started=False,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    deltas = _extract_text_deltas(events)
    full = "".join(deltas)
    # 正常文字在前后
    assert "我会先扫全部 namespace" in full or "我会先扫全部 namespace" in "".join(deltas[:-1])  # 容忍 buffer hold 一点
    assert "最终结论" in full or "最终结论" in buffers.get("msg-1", "")
    # phantom call 在中间被 strip
    assert "<tool_call>" not in full
    assert "call:foo" not in full


def test_message_id_change_clears_old_buffer():
    """新的 message_id 出现时,旧 message 的 buffer 要清掉(消息结束,tail 没用了)。"""
    from ag_ui.encoder import EventEncoder

    graph = _make_basic_graph()
    encoder = EventEncoder()
    buffers: dict = {"msg-old": "<tool_call>incomplete..."}

    # 新的 chunk 含 phantom call(故意只开不合),让"msg-new"也 hold 在 buffer
    events, new_mid, _, _ = graph._handle_chat_model_stream_content(
        chunk=_chunk_with_content("<tool_call>incomplete"),
        encoder=encoder,
        run_id="t1",
        current_message_id="msg-new",
        message_started=False,
        show_think=True,
        thinking_started=False,
        text_strip_buffers=buffers,
    )
    # 旧 buffer 被清,新 buffer 是 "msg-new"(hold 未闭合 phantom)
    assert "msg-old" not in buffers, "旧 message 的 tail buffer 必须清掉"
    assert "msg-new" in buffers
    assert "<tool_call>" in buffers["msg-new"]
