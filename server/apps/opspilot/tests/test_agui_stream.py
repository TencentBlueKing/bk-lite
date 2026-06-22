import asyncio
import json
from types import SimpleNamespace

import pytest

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.chain.graph import BasicGraph


class _FakeCompiledGraph:
    def __init__(self, events):
        self._events = events

    async def astream_events(self, *_args, **_kwargs):
        for event in self._events:
            yield event


class _FakeBasicGraph(BasicGraph):
    def __init__(self, events):
        self._events = events

    async def compile_graph(self, _request):
        return _FakeCompiledGraph(self._events)


def _parse_sse_payloads(lines):
    payloads = []
    for line in lines:
        if not line.startswith("data: "):
            continue
        payloads.append(json.loads(line[6:].strip()))
    return payloads


@pytest.fixture
def settings():
    class _Settings:
        MIDDLEWARE = []
        CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

    return _Settings()


def test_agui_stream_stops_forwarding_text_after_tool_call_chunks(monkeypatch):
    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="第一段检查结果",
                        tool_call_chunks=[],
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="",
                        tool_call_chunks=[
                            {"id": "choice-1", "name": "request_user_choice"},
                        ],
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="第二段重复检查结果",
                        tool_call_chunks=[],
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "choice-1",
                                "name": "request_user_choice",
                                "args": {"question": "请选择修复展示方式"},
                            }
                        ]
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-1", extra_config={})

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    event_types = [payload["type"] for payload in payloads]

    assert event_types.count("TEXT_MESSAGE_CONTENT") == 1
    assert [payload["delta"] for payload in payloads if payload["type"] == "TEXT_MESSAGE_CONTENT"] == ["第一段检查结果"]


def test_no_duplicate_message_when_streaming_and_chat_model_end_has_text(monkeypatch):
    """当 on_chat_model_stream 已发过文本内容时，on_chat_model_end 不应再重复发送 TEXT_MESSAGE_START/CONTENT/END。

    复现场景：LLM 流式输出后，on_chat_model_end 的 output.content 不为空且无 tool_calls，
    导致 _handle_chat_model_end_event 重复 emit 一整段消息。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    full_text = "已为您生成报告，点击下载。"
    # 分两个 chunk 流式输出
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="已为您生成报告，",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="点击下载。",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            # on_chat_model_end 携带完整文本（无 tool_calls）—— 触发 bug 的条件
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=full_text,
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-dup", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    event_types = [p["type"] for p in payloads]

    # TEXT_MESSAGE_START/END 各只能出现一次
    assert event_types.count("TEXT_MESSAGE_START") == 1, f"Expected 1 TEXT_MESSAGE_START, got: {event_types}"
    assert event_types.count("TEXT_MESSAGE_END") == 1, f"Expected 1 TEXT_MESSAGE_END, got: {event_types}"
    # 流式内容片段拼接后等于完整文本，不应出现整体重复
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(content_deltas) == full_text, f"Content mismatch: {''.join(content_deltas)!r}"
