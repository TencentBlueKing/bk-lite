"""OpenAI SSE 与 AGUI 流式协议的可见内容/思考内容契约。"""

import json

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.utils import agui_chat, sse_chat, stream_common


pytestmark = pytest.mark.unit


def parse_sse(line):
    assert line.startswith("data: ")
    return json.loads(line[6:])


def test_think_filter_hides_tagged_reasoning_and_preserves_visible_text():
    state = ("", False, True, True)
    output, buffer, in_think, first, has_tags = (
        stream_common.process_think_content(
            "<think>inspect internal state",
            state[0],
            state[1],
            state[2],
            False,
            state[3],
        )
    )
    assert output == ""
    assert in_think is True

    output, buffer, in_think, first, has_tags = (
        stream_common.process_think_content(
            "</think>database is healthy and ready",
            buffer,
            in_think,
            first,
            False,
            has_tags,
        )
    )

    assert "inspect internal state" not in output
    assert output + buffer == "database is healthy and ready"
    assert in_think is False


def test_think_split_emits_reasoning_and_visible_channels_separately():
    visible, thinking, buffer, in_think, first, has_tags = (
        stream_common.split_think_content(
            "preface<think>check logs</think>service healthy",
            "",
            False,
            True,
            True,
        )
    )

    assert visible == "prefaceservice healthy"
    assert thinking == "check logs"
    assert buffer == ""
    assert in_think is False
    assert first is False
    assert has_tags is True


def test_think_passthrough_keeps_content_when_visibility_enabled():
    result = stream_common.process_think_content(
        "<think>visible reasoning</think>",
        "",
        False,
        True,
        True,
        True,
    )

    assert result[0] == "<think>visible reasoning</think>"
    assert result[3] is False


@pytest.mark.asyncio
async def test_openai_agent_stream_filters_thinking_and_replays_custom_events():
    class Graph:
        async def agui_stream(self, _request):
            yield "event: ignored\n\n"
            yield "data: not-json\n\n"
            yield 'data: {"type":"CUSTOM","name":"browser_step","step":1}\n\n'
            yield (
                'data: {"type":"TEXT_MESSAGE_CONTENT",'
                '"delta":"<think>internal</think>database healthy"}\n\n'
            )

    events = []
    async for item in sse_chat._generate_agent_stream(
        Graph(),
        {"message": "inspect"},
        "ops",
        show_think=False,
    ):
        events.append(item)

    chunks = [
        parse_sse(item)
        for item in events
        if isinstance(item, str)
        and '"chat.completion.chunk"' in item
    ]
    visible = "".join(
        chunk["choices"][0]["delta"]["content"] for chunk in chunks
    )
    assert "internal" not in visible
    assert visible == "database healthy"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert any(
        isinstance(item, str) and '"browser_step"' in item
        for item in events
    )
    assert events[-1] == (
        "STATS",
        "<think>internal</think>database healthy",
    )


@pytest.mark.asyncio
async def test_openai_agent_stream_maps_runtime_errors_to_terminal_chunk():
    class BrokenGraph:
        async def agui_stream(self, _request):
            raise RuntimeError("provider unavailable")
            yield  # pragma: no cover

    events = [
        event
        async for event in sse_chat._generate_agent_stream(
            BrokenGraph(),
            {},
            "ops",
            show_think=False,
        )
    ]

    error = parse_sse(events[0])
    assert error["choices"][0]["finish_reason"] == "stop"
    assert "provider unavailable" in error["choices"][0]["delta"]["content"]
    assert events[-1] == ("STATS", "")


@pytest.mark.asyncio
async def test_error_stream_response_has_terminal_done_frame_and_headers():
    response = sse_chat.create_error_stream_response("invalid model")
    frames = [
        frame.decode() if isinstance(frame, bytes) else frame
        async for frame in response.streaming_content
    ]

    assert json.loads(frames[0][6:]) == {
        "result": False,
        "message": "invalid model",
        "error": True,
    }
    assert frames[1] == "data: [DONE]\n\n"
    assert response["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert response["X-Accel-Buffering"] == "no"


def test_agui_native_thinking_event_respects_model_capability_and_visibility():
    assert agui_chat._supports_thinking_events(
        type("Request", (), {"model": "qwen3-32b"})()
    )
    state = agui_chat._init_agui_stream_state()
    hidden, _ = agui_chat._handle_agui_data_event(
        {
            "type": "THINKING_TEXT_MESSAGE_CONTENT",
            "delta": "secret reasoning",
            "timestamp": 10,
        },
        state,
        show_think=False,
        enable_thinking_split=True,
    )
    visible, _ = agui_chat._handle_agui_data_event(
        {
            "type": "THINKING_TEXT_MESSAGE_CONTENT",
            "delta": "visible reasoning",
            "timestamp": 11,
        },
        state,
        show_think=True,
        enable_thinking_split=True,
    )

    assert hidden == ""
    assert parse_sse(visible) == {
        "type": "THINKING",
        "delta": "visible reasoning",
        "timestamp": 11,
    }


def test_agui_post_tool_preamble_is_thinking_and_result_stays_visible():
    state = agui_chat._init_agui_stream_state()
    start, _ = agui_chat._handle_agui_data_event(
        {"type": "TEXT_MESSAGE_START", "message_id": "m-1"},
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    content, _ = agui_chat._handle_agui_data_event(
        {
            "type": "TEXT_MESSAGE_CONTENT",
            "message_id": "m-1",
            "delta": "Thinking about the next tool",
        },
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    _tool, flushed = agui_chat._handle_agui_data_event(
        {"type": "TOOL_CALL_START", "parent_message_id": "m-1"},
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    assert parse_sse(start)["type"] == "TEXT_MESSAGE_START"
    assert content == ""
    assert parse_sse(flushed[0])["delta"] == "Thinking about the next tool"

    agui_chat._handle_agui_data_event(
        {"type": "TOOL_CALL_RESULT"},
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    agui_chat._handle_agui_data_event(
        {"type": "TEXT_MESSAGE_START", "message_id": "m-2"},
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    buffered, _ = agui_chat._handle_agui_data_event(
        {
            "type": "TEXT_MESSAGE_CONTENT",
            "message_id": "m-2",
            "delta": "根据工具结果，我已经获取到了状态。数据库健康。",
            "timestamp": 12,
        },
        state,
        show_think=True,
        enable_thinking_split=True,
    )
    _end, final_lines = agui_chat._handle_agui_data_event(
        {
            "type": "TEXT_MESSAGE_END",
            "message_id": "m-2",
            "timestamp": 13,
        },
        state,
        show_think=True,
        enable_thinking_split=True,
    )

    assert buffered == ""
    parsed = [parse_sse(line) for line in final_lines]
    assert parsed[0]["type"] == "THINKING"
    assert "根据工具结果" in parsed[0]["delta"]
    assert parsed[1]["type"] == "TEXT_MESSAGE_CONTENT"
    assert parsed[1]["delta"] == "数据库健康。"


def test_agui_hidden_thinking_strips_post_tool_meta_preamble():
    state = agui_chat._init_agui_stream_state()
    state["post_tool_result_seen"] = True
    agui_chat._handle_agui_data_event(
        {"type": "TEXT_MESSAGE_START", "message_id": "m-3"},
        state,
        show_think=False,
        enable_thinking_split=False,
    )
    agui_chat._handle_agui_data_event(
        {
            "type": "TEXT_MESSAGE_CONTENT",
            "message_id": "m-3",
            "delta": "根据返回结果，我已经完成检查。服务运行正常。",
        },
        state,
        show_think=False,
        enable_thinking_split=False,
    )
    _end, lines = agui_chat._handle_agui_data_event(
        {"type": "TEXT_MESSAGE_END", "message_id": "m-3"},
        state,
        show_think=False,
        enable_thinking_split=False,
    )

    assert [parse_sse(line)["delta"] for line in lines] == [
        "服务运行正常。"
    ]
