"""循环内窗口闸：每次模型调用前 compact，供应商超窗只重试一次。"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool

from apps.opspilot.metis.llm.chain.context_usage import CONTEXT_USAGE_EVENT
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.prepare_llm_context import CLEARED_TOOL_RESULT_PLACEHOLDER
from apps.opspilot.metis.llm.chain.token_utils import count_llm_request_tokens, count_message_tokens
from apps.opspilot.metis.llm.middleware.context_window import _RETRY_LOG_TEMPLATE, ContextWindowMiddleware

pytestmark = pytest.mark.unit

_SECRET = "sk-context-window-PROMPT-SENTINEL"


def _echo_tool():
    def _run() -> str:
        return "ok"

    return StructuredTool.from_function(func=_run, name="echo", description="echo")


def _model_request(messages, tools=None):
    return ModelRequest(
        model=SimpleNamespace(),
        messages=messages,
        system_prompt=None,
        tool_choice=None,
        tools=tools or [],
        response_format=None,
        state={},
        runtime=SimpleNamespace(),
        model_settings={},
    )


@pytest.mark.asyncio
async def test_middleware_compacts_on_later_inner_loop_call():
    history = []
    for index in range(6):
        history.append(HumanMessage(content=f"turn-{index} " + ("detail " * 40)))
        history.append(AIMessage(content=f"ack-{index} " + ("reply " * 40)))
    first_messages = [SystemMessage(content="system"), HumanMessage(content="start")]
    second_messages = [SystemMessage(content="system"), *history, HumanMessage(content="CURRENT_QUESTION_MUST_STAY")]
    message_tokens = count_message_tokens(second_messages, "gpt-4o")
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 80_000},
        compaction_enabled=True,
        compaction_max_token_threshold=max(message_tokens // 3, 20),
        compaction_keep_recent_messages=2,
        compaction_summary_max_tokens=40,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    isolated = AsyncMock()
    isolated.ainvoke.return_value = MagicMock(content="Prior turns summarized.")
    middleware = ContextWindowMiddleware(graph_request=request, isolated_llm=isolated)
    seen = []

    async def handler(model_request):
        seen.append(list(model_request.messages))
        return ModelResponse(result=[AIMessage(content="ok")])

    await middleware.awrap_model_call(_model_request(first_messages), handler)
    isolated.ainvoke.assert_not_called()

    await middleware.awrap_model_call(_model_request(second_messages), handler)
    isolated.ainvoke.assert_called_once()
    assert seen[1][-1].content == "CURRENT_QUESTION_MUST_STAY"
    assert any(
        isinstance(message, HumanMessage) and ("摘要" in str(message.content) or "summar" in str(message.content).lower()) for message in seen[1]
    )


@pytest.mark.asyncio
async def test_middleware_retries_once_after_provider_context_error(caplog):
    blob = "TOOL_BODY_" + ("n" * 200)
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="CURRENT_QUESTION_MUST_STAY"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c0"}]),
        ToolMessage(content=blob, tool_call_id="c0", name="echo"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c1"}]),
        ToolMessage(content=blob, tool_call_id="c1", name="echo"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c2"}]),
        ToolMessage(content=blob, tool_call_id="c2", name="echo"),
    ]
    packet = count_llm_request_tokens(messages, None, "gpt-4o")
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": packet + 80},
        compaction_enabled=True,
        compaction_max_token_threshold=packet + 40,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    middleware = ContextWindowMiddleware(graph_request=request, isolated_llm=None)
    calls = []

    async def handler(model_request):
        calls.append(list(model_request.messages))
        if len(calls) == 1:
            raise RuntimeError(f"maximum context length exceeded {_SECRET}")
        return ModelResponse(result=[AIMessage(content="ok")])

    caplog.set_level(logging.WARNING, logger="opspilot")
    response = await middleware.awrap_model_call(_model_request(messages, [_echo_tool()]), handler)

    assert response.result[0].content == "ok"
    assert len(calls) == 2
    retry_tools = [message for message in calls[1] if isinstance(message, ToolMessage)]
    assert retry_tools
    assert all(message.content == CLEARED_TOOL_RESULT_PLACEHOLDER for message in retry_tools)
    records = [record for record in caplog.records if record.msg == _RETRY_LOG_TEMPLATE]
    assert len(records) == 1
    assert records[0].args == ("RuntimeError",)
    rendered = records[0].getMessage()
    assert _SECRET not in rendered
    assert "maximum context length exceeded" not in rendered


@pytest.mark.asyncio
async def test_middleware_emits_bounded_context_usage_event():
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content=f"CURRENT_QUESTION {_SECRET}"),
    ]
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 6_800, "context_window_tokens": 8_000},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    middleware = ContextWindowMiddleware(graph_request=request, isolated_llm=None)

    async def handler(model_request):
        return ModelResponse(result=[AIMessage(content="ok")])

    with patch(
        "apps.opspilot.metis.llm.middleware.context_window.adispatch_custom_event",
        new_callable=AsyncMock,
    ) as emit:
        await middleware.awrap_model_call(_model_request(messages), handler)

    emit.assert_awaited()
    name, payload = emit.await_args.args
    assert name == CONTEXT_USAGE_EVENT
    assert payload["input_working_tokens"] == 6_800
    assert payload["window_tokens"] == 8_000
    assert payload["packet_tokens"] > 0
    assert _SECRET not in str(payload)
    assert "CURRENT_QUESTION" not in str(payload)


@pytest.mark.asyncio
async def test_middleware_usage_emit_failure_logs_type_not_payload(caplog):
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content=f"CURRENT_QUESTION {_SECRET}"),
    ]
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 6_800, "context_window_tokens": 8_000},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    middleware = ContextWindowMiddleware(graph_request=request, isolated_llm=None)

    async def handler(model_request):
        return ModelResponse(result=[AIMessage(content="ok")])

    caplog.set_level(logging.DEBUG, logger="opspilot")
    with patch(
        "apps.opspilot.metis.llm.middleware.context_window.adispatch_custom_event",
        new=AsyncMock(side_effect=RuntimeError("no parent run id")),
    ):
        await middleware.awrap_model_call(_model_request(messages), handler)

    records = [record for record in caplog.records if record.msg.startswith("event=llm_context_usage_emit_skipped")]
    assert len(records) == 1
    assert records[0].args == ("RuntimeError",)
    rendered = records[0].getMessage()
    assert _SECRET not in rendered
    assert "CURRENT_QUESTION" not in rendered
    assert "no parent run id" not in rendered


@pytest.mark.asyncio
async def test_middleware_usage_event_is_visible_in_astream_events():
    from langchain_core.runnables import RunnableLambda

    messages = [
        SystemMessage(content="system"),
        HumanMessage(content=f"CURRENT_QUESTION {_SECRET}"),
    ]
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 6_800, "context_window_tokens": 8_000},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    middleware = ContextWindowMiddleware(graph_request=request, isolated_llm=None)

    async def _invoke(_input, config):
        async def handler(model_request):
            return ModelResponse(result=[AIMessage(content="ok")])

        return await middleware.awrap_model_call(_model_request(messages), handler)

    seen = []
    async for event in RunnableLambda(_invoke).astream_events({}, version="v2"):
        if event.get("event") == "on_custom_event":
            seen.append(event)

    usage_events = [event for event in seen if event.get("name") == CONTEXT_USAGE_EVENT]
    assert len(usage_events) == 1
    data = usage_events[0].get("data")
    assert data["input_working_tokens"] == 6_800
    assert data["packet_tokens"] > 0
    assert _SECRET not in str(data)
    assert "CURRENT_QUESTION" not in str(data)
