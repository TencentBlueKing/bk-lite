import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

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


def test_non_streaming_final_text_after_tool_result_is_forwarded(monkeypatch):
    """工具调用前已有流式内容时，工具后的非流式最终回答不能被重复内容保护误吞。"""

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
                        content="我先访问页面。",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="",
                        tool_call_chunks=[
                            {"id": "tool-1", "name": "execute"},
                        ],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "execute",
                                "args": {"command": "markitdown https://www.baidu.com"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_tool_end",
                "name": "execute",
                "run_id": "run-tool-1",
                "data": {"output": "# 百度一下\n\n页面内容"},
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="已访问并转换为 markdown：# 百度一下\n\n页面内容",
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-final-after-tool", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    assert "已访问并转换为 markdown" in "".join(content_deltas)


def test_tool_end_result_is_forwarded_when_event_name_does_not_match_tool_call(monkeypatch):
    """LangGraph 的 on_tool_end 名称可能不是模型 tool_call 名称，结果事件仍应回填到最近运行中的工具。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "execute",
                                "args": {"command": "markitdown https://www.baidu.com > baidu.md"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_tool_start",
                "name": "RunnableCallable",
                "run_id": "run-tool-1",
                "data": {"input": {"command": "markitdown https://www.baidu.com > baidu.md"}},
            },
            {
                "event": "on_tool_end",
                "name": "RunnableCallable",
                "run_id": "run-tool-1",
                "data": {"output": "converted markdown"},
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-tool-result", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]

    assert len(tool_results) == 1
    assert tool_results[0]["toolCallId"] == "tool-1"
    assert tool_results[0]["content"] == "converted markdown"


def test_chain_end_tool_messages_are_forwarded_as_tool_results(monkeypatch):
    """DeepAgent 内部工具结果只出现在 output.messages 时，也要转成前端可见的工具结果。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "execute",
                                "args": {"command": "markitdown https://www.baidu.com -o baidu.md"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            ToolMessage(content="converted markdown", tool_call_id="tool-1"),
                            AIMessage(content="已转换完成，页面内容如下：converted markdown"),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-chain-end-tool-result", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    assert len(tool_results) == 1
    assert tool_results[0]["toolCallId"] == "tool-1"
    assert tool_results[0]["content"] == "converted markdown"
    assert "已转换完成" in "".join(content_deltas)


def test_chain_end_only_forwards_latest_ai_text_after_tool_result(monkeypatch):
    """on_chain_end 可能携带整段历史 messages，只能转发工具结果之后的最后一条 AI 文本。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    repeated_answer = "以下是访问 https://www.baidu.com 后转换成的 Markdown 内容："
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "execute",
                                "args": {"command": "markitdown https://www.baidu.com -o baidu.md"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(content=repeated_answer),
                            ToolMessage(content="converted markdown", tool_call_id="tool-1"),
                            AIMessage(content=repeated_answer),
                            AIMessage(content=repeated_answer),
                            AIMessage(content=repeated_answer),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-chain-end-dedupe-text", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    assert content_deltas == [repeated_answer]
