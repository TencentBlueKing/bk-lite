"""AGUI 流式状态机特征测试（行为锁定，重构前基线）。

被测对象：``apps.opspilot.utils.agui_chat._handle_agui_data_event`` 及其
``AguiStreamState`` 状态机——即 SSE 后处理层（think 事件路由、工具结果后的
桥接型前言 preamble 剥离、pending 缓冲的 flush 顺序）。

与同目录的 ``test_agui_stream.py`` 互补：那里测 ``graph.agui_stream`` 产出的
**原始 AGUI 事件**；这里测 agui_chat 把这些事件转成**最终 SSE 行**的状态机分支。
该状态机是 complexity review 标记的高风险重构点（pending_phase /
buffer_pre_tool_content / emit_pending_as_thinking 多标志交织），拆分前先用本文件
锁住现有逐事件输出行为。

均为纯函数级测试：不碰 DB / IO，只把事件 dict 序列喂给状态机并断言输出。
"""

import json

from apps.opspilot.utils.agui_chat import _handle_agui_data_event, _init_agui_stream_state


def _run_events(events, show_think, enable_thinking_split=False):
    """按 ``_generate_agui_stream`` 的产出顺序（先 immediate_lines、后 output_line）
    把一串 AGUI 事件喂给状态机，收集所有 SSE 行并解析为 payload 列表。"""
    state = _init_agui_stream_state()
    lines = []
    for event in events:
        output_line, immediate_lines = _handle_agui_data_event(event, state, show_think, enable_thinking_split)
        lines.extend(immediate_lines)
        if output_line:
            lines.append(output_line)

    payloads = []
    for line in lines:
        assert line.startswith("data: "), f"非法 SSE 行: {line!r}"
        payloads.append(json.loads(line[len("data: ") :].strip()))
    return payloads


def _deltas_of(payloads, msg_type):
    return [p.get("delta", "") for p in payloads if p.get("type") == msg_type]


def _types_of(payloads):
    return [p.get("type") for p in payloads]


class TestThinkingEventRouting:
    """THINKING_* 事件按 show_think 路由。"""

    def test_thinking_content_dropped_when_show_think_false(self):
        """假设 show_think=False；当收到 THINKING_TEXT_MESSAGE_CONTENT；那么不产出任何 SSE 行。"""
        payloads = _run_events(
            [{"type": "THINKING_TEXT_MESSAGE_CONTENT", "delta": "内部思考", "timestamp": 1}],
            show_think=False,
        )
        assert payloads == []

    def test_thinking_content_forwarded_as_thinking_when_show_think_true(self):
        """假设 show_think=True；当收到 THINKING_TEXT_MESSAGE_CONTENT；那么产出 1 个 THINKING 事件且 delta 不变。"""
        payloads = _run_events(
            [{"type": "THINKING_TEXT_MESSAGE_CONTENT", "delta": "内部思考", "timestamp": 1}],
            show_think=True,
        )
        assert len(payloads) == 1
        assert payloads[0]["type"] == "THINKING"
        assert payloads[0]["delta"] == "内部思考"

    def test_thinking_start_end_are_suppressed(self):
        """THINKING_TEXT_MESSAGE_START / _END 不直接转发（无论 show_think 取值）。"""
        for show_think in (True, False):
            payloads = _run_events(
                [
                    {"type": "THINKING_TEXT_MESSAGE_START", "message_id": "m1"},
                    {"type": "THINKING_TEXT_MESSAGE_END", "message_id": "m1"},
                ],
                show_think=show_think,
            )
            assert payloads == [], f"show_think={show_think} 时不应产出"


class TestPlainContentPassthrough:
    """无 think 标签、无工具的普通文本应原样透传。"""

    def test_plain_text_passes_through(self):
        """假设 show_think=False；当一段普通文本流过 START/CONTENT/END；那么正文原样输出一次。"""
        events = [
            {"type": "TEXT_MESSAGE_START", "message_id": "m1"},
            {"type": "TEXT_MESSAGE_CONTENT", "message_id": "m1", "delta": "hello world", "timestamp": 1},
            {"type": "TEXT_MESSAGE_END", "message_id": "m1"},
        ]
        payloads = _run_events(events, show_think=False)

        assert "".join(_deltas_of(payloads, "TEXT_MESSAGE_CONTENT")) == "hello world"
        types = _types_of(payloads)
        assert types.count("TEXT_MESSAGE_START") == 1
        assert types.count("TEXT_MESSAGE_END") == 1


class TestPostToolPreambleStripping:
    """工具结果后的桥接型前言处理。"""

    def test_bridge_preamble_stripped_when_show_think_false(self):
        """假设 show_think=False；当工具结果后模型先说一句"好的，我已经获取到数据。"再给正文；
        那么前言被剥离，只输出正文"实际答案"；工具结果行仍转发。"""
        events = [
            {"type": "TOOL_CALL_RESULT", "tool_call_id": "t1", "content": "raw"},
            {"type": "TEXT_MESSAGE_START", "message_id": "m1"},
            {"type": "TEXT_MESSAGE_CONTENT", "message_id": "m1", "delta": "好的，我已经获取到数据。实际答案", "timestamp": 1},
            {"type": "TEXT_MESSAGE_END", "message_id": "m1"},
        ]
        payloads = _run_events(events, show_think=False)

        assert "".join(_deltas_of(payloads, "TEXT_MESSAGE_CONTENT")) == "实际答案"
        assert any(p["type"] == "TOOL_CALL_RESULT" for p in payloads)


class TestToolCallLinesForwarded:
    """工具调用相关事件应透传给前端。"""

    def test_tool_call_events_are_forwarded(self):
        """TOOL_CALL_START / TOOL_CALL_END / TOOL_CALL_RESULT 均原样转发。"""
        events = [
            {"type": "TOOL_CALL_START", "tool_call_id": "t1", "tool_call_name": "search"},
            {"type": "TOOL_CALL_END", "tool_call_id": "t1"},
            {"type": "TOOL_CALL_RESULT", "tool_call_id": "t1", "content": "result"},
        ]
        payloads = _run_events(events, show_think=False)

        types = _types_of(payloads)
        assert "TOOL_CALL_START" in types
        assert "TOOL_CALL_END" in types
        assert "TOOL_CALL_RESULT" in types
