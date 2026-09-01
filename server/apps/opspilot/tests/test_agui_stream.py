import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Overwrite

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ChatHistory
from apps.opspilot.metis.llm.chain.graph import BasicGraph
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator


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


class _FakeExecuteGraph(BasicGraph):
    async def compile_graph(self, _request):
        return object()

    async def invoke(
        self,
        _graph,
        _request,
        stream_mode="values",
        extra_configurable=None,
    ):
        accumulator = extra_configurable["token_usage_accumulator"]
        accumulator.middleware_tracking = True
        accumulator.add(
            "call-1",
            AIMessage(
                content="先查询事件",
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                },
            ),
            visible_tools=["list_kubernetes_events"],
        )
        accumulator.add(
            "call-2",
            AIMessage(
                content="根因分析完成",
                usage_metadata={
                    "input_tokens": 160,
                    "output_tokens": 30,
                    "total_tokens": 190,
                },
            ),
            visible_tools=["get_kubernetes_pod_logs"],
        )
        return {"messages": [AIMessage(content="根因分析完成")]}


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


def test_agui_stream_suppresses_narration_when_turn_has_tool_calls(monkeypatch):
    """同一轮先流式旁白再 tool_calls：正文不展示旁白，只保留工具事件。"""

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
                        content="The parameters were passed incorrectly. Let me retry.",
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
                            {"id": "tool-1", "name": "analyze_deployment_configurations"},
                        ],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="The parameters were passed incorrectly. Let me retry.",
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "analyze_deployment_configurations",
                                "args": {"namespace": "bklite-prod"},
                            }
                        ],
                    )
                },
            },
            {
                "event": "on_tool_end",
                "name": "analyze_deployment_configurations",
                "run_id": "run-tool-1",
                "data": {"output": "probe failure evidence"},
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="本步骤结论：未执行恢复操作。",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="本步骤结论：未执行恢复操作。",
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-suppress-narration", extra_config={})

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    tool_starts = [p for p in payloads if p["type"] == "TOOL_CALL_START"]

    assert text_deltas == ["本步骤结论：未执行恢复操作。"]
    assert any(p.get("toolCallName") == "analyze_deployment_configurations" for p in tool_starts)
    assert all("parameters were passed incorrectly" not in (d or "") for d in text_deltas)


def test_agui_stream_show_think_false_suppresses_long_narration_before_tools(monkeypatch):
    """show_think=False：长旁白即使超过开播阈值也不得进正文，等 tool 后整段丢弃。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    long_narration = (
        "I'll generate the monthly report based on the fault archives. "
        "Let me analyze the data: RC-NEW-001 FailedKillPod, RC-NEW-002 Unhealthy, "
        "metrics calculation and event type distribution before calling the tool."
    )
    assert len(long_narration) >= 96

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=long_narration,
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
                        tool_call_chunks=[{"id": "tool-att", "name": "generate_attachment_file"}],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=long_narration,
                        tool_calls=[
                            {
                                "id": "tool-att",
                                "name": "generate_attachment_file",
                                "args": {"filename": "report.md"},
                            }
                        ],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-long-narration",
        extra_config={"show_think": False},
    )

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == []
    assert any(p.get("toolCallName") == "generate_attachment_file" for p in payloads if p["type"] == "TOOL_CALL_START")
    assert all(p.get("name") != "assistant_text_retract" for p in payloads if p["type"] == "CUSTOM")


def test_agui_stream_show_think_false_still_emits_plain_answer_at_end(monkeypatch):
    """show_think=False 的纯文本轮：不提前开播，chat_model_end 再发出全文。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    answer = "广州是广东省省会，" + ("历史悠久文化多元。" * 20)
    assert len(answer) >= 96

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=answer[:40],
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=answer[40:],
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=answer,
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-plain-no-think",
        extra_config={"show_think": False},
    )

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(text_deltas) == answer
    assert sum(1 for p in payloads if p["type"] == "TEXT_MESSAGE_START") == 1


@pytest.mark.parametrize(
    ("capabilities", "expected_started_count"),
    [
        ([], 0),
        (["repair_diff_report"], 0),
        (["config_analysis_report"], 0),
    ],
)
def test_agui_stream_starts_report_only_for_matching_capability(
    monkeypatch,
    capabilities,
    expected_started_count,
):
    """AG-UI 通用流不根据 capability 或工具名推断报告生命周期。"""

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
                        content="",
                        tool_call_chunks=[
                            {"id": "tool-report-1", "name": "analyze_deployment_configurations"},
                        ],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="",
                        tool_calls=[
                            {
                                "id": "tool-report-1",
                                "name": "analyze_deployment_configurations",
                                "args": {"namespace": "production"},
                            }
                        ],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-report-start",
        extra_config={
            "execution_id": "exec-report-start",
            "skill_package_capabilities": capabilities,
        },
    )

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    report_starts = [payload for payload in payloads if payload.get("type") == "CUSTOM" and payload.get("name") == "report_started"]

    assert len(report_starts) == expected_started_count


def test_agui_stream_preserves_text_and_forwards_completed_reports_in_event_order(monkeypatch):
    """正文照常输出，完成的结构化报告按来源事件顺序转发。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    analyze_tool_call = {
        "id": "tool-analysis-1",
        "name": "analyze_deployment_configurations",
        "args": {"namespace": "production"},
    }
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="",
                        tool_call_chunks=[analyze_tool_call],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {"output": SimpleNamespace(content="", tool_calls=[analyze_tool_call])},
            },
            {
                "event": "on_custom_event",
                "name": "config_analysis_report",
                "data": {
                    "report_id": "config_analysis_report_exec-report-sequence",
                    "summary": {"total": 3},
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="Kubernetes 集群工作负载配置巡检最终报告",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="Kubernetes 集群工作负载配置巡检最终报告",
                        tool_calls=[],
                    )
                },
            },
            {
                "event": "on_custom_event",
                "name": "user_choice_request",
                "data": {
                    "choice_id": "repair-choice-1",
                    "question": "请选择修复展示方式",
                    "options": [{"label": "全部一次性展示", "value": "all"}],
                },
            },
            {
                "event": "on_tool_start",
                "name": "generate_repair_report",
                "run_id": "repair-tool-run-1",
                "data": {"input": {"group_by": "all"}},
            },
            {
                "event": "on_custom_event",
                "name": "repair_diff_report",
                "data": {
                    "report_id": "repair_diff_report_exec-report-sequence",
                    "items": [{"resource": "Deployment/api"}],
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-report-sequence",
        extra_config={
            "execution_id": "exec-report-sequence",
            "skill_package_capabilities": [
                "config_analysis_report",
                "repair_diff_report",
            ],
        },
    )

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    lifecycle_events = [
        payload for payload in payloads if payload.get("type") == "CUSTOM" and payload.get("name") in {"report_queued", "report_started"}
    ]
    analysis_report_index = next(
        index for index, payload in enumerate(payloads) if payload.get("type") == "CUSTOM" and payload.get("name") == "config_analysis_report"
    )
    summary_text_index = next(
        index
        for index, payload in enumerate(payloads)
        if payload.get("type") == "TEXT_MESSAGE_CONTENT" and "巡检最终报告" in str(payload.get("delta") or "")
    )
    repair_report_index = next(
        index for index, payload in enumerate(payloads) if payload.get("type") == "CUSTOM" and payload.get("name") == "repair_diff_report"
    )

    assert lifecycle_events == []
    assert analysis_report_index < summary_text_index < repair_report_index


@pytest.mark.parametrize(
    "terminal_source",
    ["completed", "missing_report", "interrupted"],
)
def test_agui_stream_does_not_synthesize_report_terminal_events(monkeypatch, terminal_source):
    """通用流不为报告补造完成、失败或取消事件。"""
    interrupt_checks = 0

    async def _interrupt_after_report_started(_execution_id):
        nonlocal interrupt_checks
        interrupt_checks += 1
        return terminal_source == "interrupted" and interrupt_checks > 1

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _interrupt_after_report_started,
    )

    events = [
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": SimpleNamespace(
                    content="",
                    tool_call_chunks=[
                        {"id": "tool-report-close", "name": "analyze_deployment_configurations"},
                    ],
                    additional_kwargs={},
                )
            },
        },
    ]
    if terminal_source == "completed":
        events.append(
            {
                "event": "on_custom_event",
                "name": "config_analysis_report",
                "data": {"report_id": "config_analysis_report_exec-report-close"},
            }
        )
    elif terminal_source == "interrupted":
        events.append(
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="不会继续处理",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            }
        )

    graph = _FakeBasicGraph(events)
    request = BasicLLMRequest(
        thread_id="thread-report-close",
        extra_config={
            "execution_id": "exec-report-close",
            "skill_package_capabilities": ["config_analysis_report"],
        },
    )

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    terminal_events = [
        payload for payload in payloads if payload.get("type") == "CUSTOM" and payload.get("name") in {"report_failed", "report_cancelled"}
    ]

    assert terminal_events == []


def test_agui_stream_stops_forwarding_text_after_tool_call_chunks(monkeypatch):
    """兼容旧用例名：有 tool_calls 的轮次不再把旁白发成 TEXT_MESSAGE。"""

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
                            {"id": "choice-1", "name": "request_user_choice"},
                        ],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="第二段重复检查结果",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="第一段检查结果第二段重复检查结果",
                        tool_calls=[
                            {
                                "id": "choice-1",
                                "name": "request_user_choice",
                                "args": {"question": "请选择修复展示方式"},
                            }
                        ],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-1", extra_config={})

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [payload["delta"] for payload in payloads if payload["type"] == "TEXT_MESSAGE_CONTENT"]
    assert text_deltas == []
    assert any(p["type"] == "TOOL_CALL_START" for p in payloads)


def test_agui_stream_goes_live_on_single_large_chunk_without_tools(monkeypatch):
    """单大片正文（Minimax 一类）：超字符阈值即开播并拆多段 CONTENT，不按模型名分支。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    big = "广州是广东省省会，" + ("历史悠久文化多元。" * 20)
    assert len(big) >= 96

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=big,
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=big,
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-minimax-like", extra_config={})

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(text_deltas) == big
    assert len(text_deltas) >= 2
    assert all(len(d) <= 64 for d in text_deltas[:-1])
    assert sum(1 for p in payloads if p["type"] == "TEXT_MESSAGE_START") == 1


def test_agui_stream_emits_plain_answer_without_tools(monkeypatch):
    """无工具的普通问答：第 2 个正文 chunk 起实时推送，chat_model_end 不重复整段。"""

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
                        content="你好，",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="这是结论。",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content="补充一句。",
                        tool_call_chunks=[],
                        additional_kwargs={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="你好，这是结论。补充一句。",
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-plain-answer", extra_config={})

    async def _collect_payloads():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect_payloads())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(text_deltas) == "你好，这是结论。补充一句。"
    # 第 2 chunk 起直播：至少拆成「前两段合并 + 后续增量」，且不得在 end 再整段重发。
    assert len(text_deltas) >= 2
    assert text_deltas[-1] == "补充一句。"
    assert sum(1 for p in payloads if p["type"] == "TEXT_MESSAGE_START") == 1
    assert sum(1 for p in payloads if p["type"] == "TEXT_MESSAGE_END") == 1


def test_agui_stream_collects_all_llm_token_usage_once_per_run(monkeypatch):
    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )
    accumulator = TokenUsageAccumulator()
    first_output = SimpleNamespace(
        content="",
        tool_calls=[],
        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    )
    second_output = SimpleNamespace(
        content="",
        tool_calls=[],
        usage_metadata=None,
        response_metadata={"token_usage": {"prompt_tokens": 20, "completion_tokens": 4}},
    )
    graph = _FakeBasicGraph(
        [
            {"event": "on_chat_model_end", "run_id": "run-1", "data": {"output": first_output}},
            {"event": "on_chat_model_end", "run_id": "run-2", "data": {"output": second_output}},
            {"event": "on_chat_model_end", "run_id": "run-1", "data": {"output": first_output}},
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-token-usage",
        extra_config={},
    )

    async def _consume():
        return [
            line
            async for line in graph.agui_stream(
                request,
                token_usage_accumulator=accumulator,
            )
        ]

    asyncio.run(_consume())

    assert accumulator.as_openai_usage() == {
        "prompt_tokens": 30,
        "completion_tokens": 6,
        "total_tokens": 36,
    }
    assert accumulator.call_count == 2
    assert [
        {
            "call_index": call["call_index"],
            "total_tokens": call["total_tokens"],
        }
        for call in accumulator.as_call_details()
    ] == [
        {"call_index": 1, "total_tokens": 12},
        {"call_index": 2, "total_tokens": 24},
    ]


def test_execute_returns_per_call_token_usage():
    response = asyncio.run(_FakeExecuteGraph().execute(BasicLLMRequest(thread_id="thread-sync-token", extra_config={})))

    assert response.llm_call_count == 2
    assert response.total_tokens == 300
    assert response.token_usage_calls == [
        {
            "call_index": 1,
            "prompt_tokens": 100,
            "completion_tokens": 10,
            "total_tokens": 110,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["list_kubernetes_events"],
        },
        {
            "call_index": 2,
            "prompt_tokens": 160,
            "completion_tokens": 30,
            "total_tokens": 190,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["get_kubernetes_pod_logs"],
        },
    ]


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


def test_chain_end_synthesizes_tool_start_when_only_tool_message_present(monkeypatch):
    """嵌套 DeepAgent 未冒泡 TOOL_CALL_START 时，chain_end 的 ToolMessage 仍应补齐 START/RESULT。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "id": "call-time-1",
                                        "name": "get_current_time",
                                        "args": {"timezone": "Asia/Shanghai"},
                                    }
                                ],
                            ),
                            ToolMessage(
                                content="2026-08-06 16:58:00",
                                tool_call_id="call-time-1",
                                name="get_current_time",
                            ),
                            AIMessage(content="现在是 2026-08-06 16:58:00"),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-chain-end-synth-tool", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    tool_starts = [p for p in payloads if p["type"] == "TOOL_CALL_START"]
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]

    assert len(tool_starts) == 1
    assert tool_starts[0]["toolCallId"] == "call-time-1"
    assert tool_starts[0]["toolCallName"] == "get_current_time"
    assert len(tool_results) == 1
    assert tool_results[0]["content"] == "2026-08-06 16:58:00"


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


def test_chain_end_does_not_duplicate_text_already_emitted_by_chat_model_end(monkeypatch):
    """on_chain_end 不应重复 emit on_chat_model_end 已经发过的非流式文本。

    复现场景:用户报告"两次重复的回答"。
    根因:工具执行后的 on_chat_model_end 携带完整 AI 文本(allow_non_streaming_text=True),
    同一份文本又出现在 on_chain_end 的 output.messages 里,_handle_chain_end_messages
    又通过 _handle_chat_model_end_event 重新发了一遍,前端看到重复。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    final_answer = "集群中所有工作负载均存在配置缺陷,详见下表..."

    graph = _FakeBasicGraph(
        [
            # 第一次 chat model end: 只有 tool_calls(让模型调用工具)
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "analyze_deployment_configurations",
                                "args": {"namespace": "production"},
                            }
                        ]
                    )
                },
            },
            # 工具执行
            {
                "event": "on_tool_end",
                "name": "analyze_deployment_configurations",
                "run_id": "run-tool-1",
                "data": {"output": "deployment config data"},
            },
            # 第二次 chat model end: 携带完整 AI 文本(非流式 adapter 路径)
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=final_answer,
                        tool_calls=[],
                    )
                },
            },
            # chain end: DeepAgent 把整段历史塞进 messages,
            # 关键:含 ToolMessage(让 chain_end handler 认为有工具结果需要回填),
            # 之后跟的 AIMessage 就是 chat_model_end 已经发过的那份文本
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(content="调用工具前的思考"),
                            ToolMessage(content="工具原始结果", tool_call_id="tool-1"),
                            AIMessage(content=final_answer),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-chain-end-no-dup-text", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    # 关键断言:同一份文本只发一次,即使它同时出现在 chat_model_end 和 chain_end
    assert (
        "".join(content_deltas) == final_answer
    ), f"Final answer should be emitted once; got {len(content_deltas)} chunk(s). chunks={content_deltas!r}"


def test_chain_end_does_not_duplicate_long_text_split_into_deltas(monkeypatch):
    """长回答被拆成多段 TEXT_MESSAGE_CONTENT 后，chain_end 仍须按全文去重。

    复现场景:用户反馈同一段「已获取集群上下文…」完整出现两次。
    根因:_AGUI_LIVE_DELTA_CHARS=64 会把 chat_model_end 的正文拆段登记指纹,
    chain_end 用整段 AIMessage.content 比对落空,又把全文再发一遍。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    final_answer = (
        "已获取集群上下文并验证连接成功。\n\n"
        "**当前步骤结果**\n"
        "- **集群实例**: Kubernetes - 2 (instance_id: kubernetes-1784018234906-56tq0t)\n"
        "- **上下文**: `orbstack`（当前使用，命名空间: default）\n"
        "- **连接状态**: 成功\n"
        "- **Kubernetes 版本**: v1.33.9+orb1\n"
        "- **平台**: linux/arm64\n"
        "- **API Server**: 可访问\n"
        "- **权限**: 有基本读取权限，namespace 访问正常\n\n"
        "集群连接与权限验证通过，可以继续后续步骤对工作负载进行配置检查。"
    )
    assert len(final_answer) > 64

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
                                "args": {"command": "kubectl get deploy -n production"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_tool_end",
                "name": "execute",
                "run_id": "run-tool-1",
                "data": {"output": "ok"},
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=final_answer,
                        tool_calls=[],
                    )
                },
            },
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            ToolMessage(content="ok", tool_call_id="tool-1"),
                            AIMessage(content=final_answer),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-long-text-no-dup", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    joined = "".join(content_deltas)

    assert joined == final_answer, (
        f"Long final answer should be emitted once; got length={len(joined)} " f"expected={len(final_answer)}; repeats={joined.count(final_answer)}"
    )
    assert joined.count("已获取集群上下文并验证连接成功。") == 1


def test_multiple_chain_end_with_same_text_only_emits_once(monkeypatch):
    """DeepAgent 父/子图会多次触发 on_chain_end,output.messages 都带同一份最终 AI 文本。

    复现场景:用户报告"两次重复的回答"。
    生产里 chain_end 1 次通常就能去重,但父图 + 子图会各发一次 chain_end,
    单纯 flag 机制(只跳过紧邻的下一个 chain_end)不够。必须用内容指纹去重,
    任何源已经 emit 过这份文本,后续 chain_end 再遇到相同内容就跳过。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    final_answer = "集群中所有工作负载均存在配置缺陷..."

    graph = _FakeBasicGraph(
        [
            # 第一次 chat model end: 调用工具
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        tool_calls=[
                            {
                                "id": "tool-1",
                                "name": "analyze_deployment_configurations",
                                "args": {"namespace": "production"},
                            }
                        ]
                    )
                },
            },
            # 工具执行
            {
                "event": "on_tool_end",
                "name": "analyze_deployment_configurations",
                "run_id": "run-tool-1",
                "data": {"output": "deployment data"},
            },
            # 第二次 chat model end: 完整 AI 文本(非流式路径)
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=final_answer,
                        tool_calls=[],
                    )
                },
            },
            # 父图 chain_end: 含 ToolMessage(触发 chain_end handler 走文本路径)
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(content="调用工具前的思考"),
                            ToolMessage(content="工具原始结果", tool_call_id="tool-1"),
                            AIMessage(content=final_answer),
                        ]
                    }
                },
            },
            # 子图 chain_end: 也带同一份最终 AI 文本
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(content=final_answer),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-multi-chain-end-dedup", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    # 关键断言:即使有多个 chain_end 同份文本,emit 仍只发生一次
    assert "".join(content_deltas) == final_answer, (
        f"Final answer should be emitted exactly once across multiple chain_end; " f"got {len(content_deltas)} chunk(s): {content_deltas!r}"
    )


def test_chain_end_unwraps_overwrite_messages(monkeypatch):
    """LangGraph 可能用 Overwrite 包裹 messages，AG-UI 应先解包再遍历。"""

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
                                "args": {"command": "date"},
                            }
                        ]
                    )
                },
            },
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": Overwrite(
                            [
                                ToolMessage(content="2026-07-07", tool_call_id="tool-1"),
                                AIMessage(content="当前时间已获取"),
                            ]
                        )
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-chain-end-overwrite", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]
    content_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    assert len(tool_results) == 1
    assert tool_results[0]["toolCallId"] == "tool-1"
    assert tool_results[0]["content"] == "2026-07-07"
    assert "当前时间已获取" in "".join(content_deltas)


def test_chain_end_emits_plain_ai_text_without_tools(monkeypatch):
    """无工具纯 AIMessage（轻量直答）在 chain_end 也应推送正文。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chain_end",
                "data": {"output": {"messages": [AIMessage(content="你好！有什么可以帮你的？")]}},
            }
        ]
    )
    request = BasicLLMRequest(thread_id="thread-plain-chain-end", extra_config={})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    text = "".join(p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT")
    assert text == "你好！有什么可以帮你的？"


def test_chain_end_does_not_replay_previous_turn_when_history_ends_with_user(monkeypatch):
    """新一轮 on_chain_end 常带完整历史且以当前 HumanMessage 结尾。

    追问「现在呢」（尤其带 page_context）时，prepare/compaction 子链结束会把
    上一轮助手正文当成 latest_plain_ai。旧逻辑会在真实流式到达前整段重放，
    前端先闪旧回答再被新 messageId 替换。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    previous_answer = "根据磁盘吞吐趋势，当前使用率 82.9%，暂不需要加磁盘。"
    current_answer = "根据当前页面快照（最近12小时），磁盘使用率仍为 82.9%。"
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            HumanMessage(content="什么时候需要加磁盘"),
                            AIMessage(content=previous_answer),
                            HumanMessage(
                                content=[
                                    {"type": "text", "text": "现在呢"},
                                    {
                                        "type": "text",
                                        "text": "<current_page>磁盘使用率: 82.9%</current_page>",
                                    },
                                ]
                            ),
                        ]
                    }
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=current_answer,
                        tool_call_chunks=[],
                        additional_kwargs={},
                        response_metadata={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=current_answer,
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-no-history-replay",
        extra_config={},
        chat_history=[
            ChatHistory(event="user", message="什么时候需要加磁盘"),
            ChatHistory(event="bot", message=previous_answer),
        ],
    )

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    text_starts = [p for p in payloads if p["type"] == "TEXT_MESSAGE_START"]
    text = "".join(p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT")

    assert previous_answer not in text
    assert current_answer in text
    assert len(text_starts) == 1


def test_chain_end_does_not_replay_add_chat_history_node(monkeypatch):
    """skill_channel chat 图顺序是 history → user_message。

    add_chat_history_node 结束时 last=上一轮助手，「仅当 last 是 AI 才当轻量直答」
    仍会把旧正文整段推出去，前端先闪旧文，等模型流式到了再 TEXT_MESSAGE_START。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    previous_answer = "根据磁盘吞吐趋势，当前使用率 82.9%，暂不需要加磁盘。"
    current_answer = "根据当前页面快照（最近12小时），磁盘使用率仍为 82.9%。"
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chain_end",
                "name": "add_chat_history_node",
                "data": {
                    "output": {
                        "messages": [
                            HumanMessage(content="什么时候需要加磁盘"),
                            AIMessage(content=previous_answer),
                        ]
                    }
                },
            },
            {
                "event": "on_chain_end",
                "name": "user_message_node",
                "data": {
                    "output": {
                        "messages": [
                            HumanMessage(content="什么时候需要加磁盘"),
                            AIMessage(content=previous_answer),
                            HumanMessage(content="现在呢"),
                        ]
                    }
                },
            },
            {
                "event": "on_chat_model_stream",
                "data": {
                    "chunk": SimpleNamespace(
                        content=current_answer,
                        tool_call_chunks=[],
                        additional_kwargs={},
                        response_metadata={},
                    )
                },
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content=current_answer,
                        tool_calls=[],
                    )
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-history-node-replay",
        extra_config={},
        chat_history=[
            ChatHistory(event="user", message="什么时候需要加磁盘"),
            ChatHistory(event="bot", message=previous_answer),
        ],
    )

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    text_starts = [p for p in payloads if p["type"] == "TEXT_MESSAGE_START"]
    text = "".join(p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT")

    assert previous_answer not in text
    assert current_answer in text
    assert len(text_starts) == 1


def test_agui_stream_emits_current_turn_identical_to_history_bot_text(monkeypatch):
    """历史助手短句不得种子本轮去重指纹。

    上一轮 bot 已说过「好的」时，本轮 on_chat_model_end 再给出「好的」仍必须
    发出一组 TEXT_MESSAGE_*；否则短重复回答会被静默丢掉。
    """

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
                    "output": SimpleNamespace(content="好的", tool_calls=[]),
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-same-short-as-history",
        extra_config={"show_think": False},
        chat_history=[
            ChatHistory(event="user", message="可以吗"),
            ChatHistory(event="bot", message="好的"),
        ],
    )

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    types = [p["type"] for p in payloads]
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]

    assert types.count("TEXT_MESSAGE_START") == 1
    assert types.count("TEXT_MESSAGE_END") == 1
    assert "".join(text_deltas) == "好的"


def test_agui_stream_warns_empty_response_even_when_history_has_bot_text(monkeypatch):
    """历史助手正文不得掩盖本轮空响应告警。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.logger.warning",
        lambda msg, *args, **_kwargs: warnings.append(msg if not args else msg % args),
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(content="", tool_calls=[]),
                },
            },
        ]
    )
    request = BasicLLMRequest(
        thread_id="thread-empty-with-history",
        extra_config={"show_think": False},
        chat_history=[
            ChatHistory(event="bot", message="好的"),
        ],
    )

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    types = [p["type"] for p in payloads]

    assert "TEXT_MESSAGE_CONTENT" not in types
    assert any("LLM 调用完成但返回空内容" in msg for msg in warnings)


def test_agui_stream_surfaces_node_llm_failure_as_run_error(monkeypatch):
    """节点内 LLM 失败不得被 _merge_async_streams 吞掉。

    回归：无工具轻量直答里 llm.astream/ainvoke 抛错时，旧实现会只发
    RUN_STARTED→RUN_FINISHED，前端空白且 llm_call_count=0，日志也看不到原因。
    """
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import HumanMessage
    from langgraph.graph import END, StateGraph

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    class BoomLLM(BaseChatModel):
        @property
        def _llm_type(self):
            return "boom"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise RuntimeError("boom: invalid api key")

    llm = BoomLLM()

    async def deep_wrapper(state, config):
        # 与轻量直答相同：节点内直接 astream
        response = None
        async for chunk in llm.astream([HumanMessage(content="hello")], config=config):
            response = chunk
        return {"messages": [response] if response is not None else []}

    class _Graph(BasicGraph):
        async def compile_graph(self, _request):
            gb = StateGraph(dict)
            gb.add_node("deep_agent_wrapper", deep_wrapper)
            gb.set_entry_point("deep_agent_wrapper")
            gb.add_edge("deep_agent_wrapper", END)
            return gb.compile()

    request = BasicLLMRequest(thread_id="thread-llm-boom", user_message="hello", extra_config={})
    accumulator = TokenUsageAccumulator()

    async def _collect():
        return _parse_sse_payloads([line async for line in _Graph().agui_stream(request, token_usage_accumulator=accumulator)])

    payloads = asyncio.run(_collect())
    types = [p["type"] for p in payloads]
    assert "RUN_ERROR" in types, f"expected RUN_ERROR, got {types}"
    err = next(p for p in payloads if p["type"] == "RUN_ERROR")
    assert "invalid api key" in (err.get("message") or "")
    assert accumulator.call_count == 0
    assert "TEXT_MESSAGE_CONTENT" not in types


def test_two_chat_model_ends_with_identical_text_emit_once(monkeypatch):
    """DeepAgent 步骤确认后再来一轮相同正文时，只推一次 TEXT_MESSAGE。

    复现：附件生成后两段一模一样的「已生成附件…」确认文案。
    """

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    answer = "已生成附件：`K8s_集群运维月报_2026-08.md`\n\n" "本月事件 25 起，根因分析 11 起，重复隐患 3 项（探针配置、KillContainer 竞态、Redis DNS 解析）。"
    tool_result = (
        '{"attachment_id": "skill_test", "filename": "K8s_集群运维月报_2026-08.md", '
        '"file_url": "/api/proxy/opspilot/bot_mgmt/workflow_attachment/download/tok/"}'
    )

    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="",
                        tool_calls=[
                            {
                                "id": "call_att_1",
                                "name": "generate_attachment_file",
                                "args": {"filename": "K8s_集群运维月报_2026-08.md"},
                            }
                        ],
                    )
                },
            },
            {
                "event": "on_tool_end",
                "name": "generate_attachment_file",
                "run_id": "run-att-1",
                "data": {"output": ToolMessage(content=tool_result, tool_call_id="call_att_1")},
            },
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(content=answer, tool_calls=[]),
                },
            },
            # 步骤结束后再一轮相同确认（此前会再推一遍 TEXT_MESSAGE）
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(content=answer, tool_calls=[]),
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-dup-confirm", extra_config={"show_think": False})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    text_deltas = [p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT"]
    assert "".join(text_deltas) == answer
    assert sum(1 for p in payloads if p["type"] == "TEXT_MESSAGE_START") == 1
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"] == tool_result
    assert "name='generate_attachment_file'" not in tool_results[0]["content"]


def test_tool_end_marks_result_sent_so_chain_end_does_not_resend(monkeypatch):
    """on_tool_end 已回填 RESULT 后，on_chain_end 不得再发同一 toolCallId 的 RESULT。"""

    async def _never_interrupted(_execution_id):
        return False

    monkeypatch.setattr(
        "apps.opspilot.metis.llm.chain.graph.is_interrupt_requested_async",
        _never_interrupted,
    )

    clean = '{"ok": true, "filename": "report.md"}'
    graph = _FakeBasicGraph(
        [
            {
                "event": "on_chat_model_end",
                "data": {
                    "output": SimpleNamespace(
                        content="",
                        tool_calls=[{"id": "tool-1", "name": "generate_attachment_file", "args": {}}],
                    )
                },
            },
            {
                "event": "on_tool_end",
                "name": "generate_attachment_file",
                "run_id": "run-1",
                "data": {"output": ToolMessage(content=clean, tool_call_id="tool-1", name="generate_attachment_file")},
            },
            {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[{"id": "tool-1", "name": "generate_attachment_file", "args": {}}],
                            ),
                            ToolMessage(content=clean, tool_call_id="tool-1"),
                            AIMessage(content="已生成附件"),
                        ]
                    }
                },
            },
        ]
    )
    request = BasicLLMRequest(thread_id="thread-tool-result-once", extra_config={"show_think": False})

    async def _collect():
        return _parse_sse_payloads([line async for line in graph.agui_stream(request)])

    payloads = asyncio.run(_collect())
    tool_results = [p for p in payloads if p["type"] == "TOOL_CALL_RESULT"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"] == clean
    assert "".join(p["delta"] for p in payloads if p["type"] == "TEXT_MESSAGE_CONTENT") == "已生成附件"
