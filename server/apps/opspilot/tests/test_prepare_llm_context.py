"""LLM 调用前 trim + compact；裁无可裁时明确失败且不截断本轮问题。"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.prepare_llm_context import CLEARED_TOOL_RESULT_PLACEHOLDER, LLMContextWindowExceeded, prepare_messages_for_llm
from apps.opspilot.metis.llm.chain.token_utils import count_llm_request_tokens, count_message_tokens, count_text_tokens, count_tool_schema_tokens


@pytest.mark.asyncio
async def test_prepare_messages_trims_history_but_keeps_current_user_text():
    current = "CURRENT_QUESTION_MUST_STAY " + ("x" * 50)
    history = "old-history " * 200
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 80_000},
        message_trim_config=MessageTrimConfig(enabled=True, max_single_message_tokens=20, image_retain_recent=0),
        compaction_enabled=False,
    )
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content=history),
        HumanMessage(content=current),
    ]

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=None)

    assert prepared[-1].content == current
    assert "CURRENT_QUESTION_MUST_STAY" in prepared[-1].content
    assert len(prepared[1].content) < len(history)


@pytest.mark.asyncio
async def test_prepare_messages_fails_when_irreducible_core_exceeds_input_working():
    current = "CURRENT_QUESTION_UNTRUNCATED " + ("q" * 200)
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 8},
        message_trim_config=MessageTrimConfig(enabled=True, max_single_message_tokens=4, image_retain_recent=0),
        compaction_enabled=False,
    )
    messages = [
        SystemMessage(content="system-core"),
        HumanMessage(content="old " * 40),
        HumanMessage(content=current),
    ]

    original_current = messages[-1].content
    with pytest.raises(LLMContextWindowExceeded) as exc_info:
        await prepare_messages_for_llm(messages, request=request, isolated_llm=None)

    assert exc_info.value.code == "llm_context_window_exceeded"
    assert messages[-1].content == original_current
    core_tokens = count_message_tokens([messages[0], messages[2]])
    assert core_tokens > 8


class _HugeLookupArgs(BaseModel):
    query: str = Field(description="HUGE_SCHEMA_PAD " + ("z" * 4000))


def _huge_lookup_tool():
    def _run(query: str) -> str:
        return query

    return StructuredTool.from_function(
        func=_run,
        name="huge_lookup",
        description="lookup",
        args_schema=_HugeLookupArgs,
    )


def test_tool_schema_tokens_count_parameters_not_just_name():
    tool = _huge_lookup_tool()
    schema_tokens = count_tool_schema_tokens([tool], "gpt-4o")
    name_only = count_text_tokens("huge_lookup\nlookup", "gpt-4o")
    assert schema_tokens > name_only
    assert schema_tokens > 800


@pytest.mark.asyncio
async def test_prepare_counts_tool_schema_when_deciding_to_compact():
    tool = _huge_lookup_tool()
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="turn-1"),
        AIMessage(content="ack-1"),
        HumanMessage(content="turn-2"),
        AIMessage(content="ack-2"),
        HumanMessage(content="CURRENT_QUESTION_MUST_STAY"),
    ]
    message_tokens = count_message_tokens(messages, "gpt-4o")
    schema_tokens = count_tool_schema_tokens([tool], "gpt-4o")
    assert schema_tokens > 800
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": 80_000},
        compaction_enabled=True,
        compaction_max_token_threshold=message_tokens,
        compaction_keep_recent_messages=2,
        compaction_summary_max_tokens=40,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    isolated = AsyncMock()
    isolated.ainvoke.return_value = MagicMock(content="Prior turns summarized.")

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=isolated, tools=[tool])

    isolated.ainvoke.assert_called_once()
    assert prepared[-1].content == "CURRENT_QUESTION_MUST_STAY"
    skipped = await prepare_messages_for_llm(messages, request=request, isolated_llm=AsyncMock(), tools=None)
    assert skipped == messages


@pytest.mark.asyncio
async def test_prepare_clears_old_tool_results_when_packet_exceeds_working_budget():
    blob = "TOOL_BODY_" + ("n" * 400)
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="CURRENT_QUESTION_MUST_STAY"),
    ]
    for index in range(8):
        messages.append(AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": f"c{index}"}]))
        messages.append(ToolMessage(content=blob, tool_call_id=f"c{index}", name="echo"))
    core = [messages[0], messages[1]]
    one_tool = count_message_tokens([messages[-1]], "gpt-4o")
    core_tokens = count_llm_request_tokens(core, None, "gpt-4o")
    full_tokens = count_llm_request_tokens(messages, None, "gpt-4o")
    input_working = core_tokens + (4 * one_tool) + 20
    assert full_tokens > input_working
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": input_working},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=None)

    assert prepared[1].content == "CURRENT_QUESTION_MUST_STAY"
    cleared = [message for message in prepared if isinstance(message, ToolMessage) and message.content == CLEARED_TOOL_RESULT_PLACEHOLDER]
    kept = [message for message in prepared if isinstance(message, ToolMessage) and message.content == blob]
    assert len(cleared) >= 4
    assert len(cleared) + len(kept) == 8
    assert count_llm_request_tokens(prepared, None, "gpt-4o") <= input_working


@pytest.mark.asyncio
async def test_prepare_fails_when_tool_schema_makes_core_unfittable():
    tool = _huge_lookup_tool()
    current = "CURRENT_QUESTION_UNTRUNCATED"
    messages = [
        SystemMessage(content="system-core"),
        HumanMessage(content=current),
    ]
    core_tokens = count_llm_request_tokens(messages, [tool], "gpt-4o")
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": max(core_tokens // 4, 8)},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )

    with pytest.raises(LLMContextWindowExceeded) as exc_info:
        await prepare_messages_for_llm(messages, request=request, isolated_llm=None, tools=[tool])

    assert exc_info.value.code == "llm_context_window_exceeded"
    assert messages[-1].content == current


def _last_human_content(messages):
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content
    return None


@pytest.mark.asyncio
async def test_prepare_shrinks_keep_recent_when_first_compact_cannot_split():
    blob = "FAT_TURN_" + ("n" * 400)
    messages = [SystemMessage(content="system")]
    for index in range(5):
        messages.append(HumanMessage(content=f"{blob}-{index}"))
        messages.append(AIMessage(content=f"{blob}-ack-{index}"))
    messages.append(HumanMessage(content="CURRENT_QUESTION_MUST_STAY"))
    full_tokens = count_llm_request_tokens(messages, None, "gpt-4o")
    core_tokens = count_llm_request_tokens([messages[0], messages[-1]], None, "gpt-4o")
    input_working = core_tokens + 80
    assert full_tokens > input_working
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": input_working},
        compaction_enabled=True,
        compaction_max_token_threshold=core_tokens + 10,
        compaction_keep_recent_messages=12,
        compaction_summary_max_tokens=40,
        message_trim_config=MessageTrimConfig(enabled=False),
    )
    isolated = AsyncMock()
    isolated.ainvoke.return_value = MagicMock(content="Prior turns summarized.")

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=isolated)

    isolated.ainvoke.assert_called()
    assert _last_human_content(prepared) == "CURRENT_QUESTION_MUST_STAY"
    assert count_llm_request_tokens(prepared, None, "gpt-4o") <= input_working
    assert any("摘要" in str(getattr(message, "content", "")) or "summar" in str(getattr(message, "content", "")).lower() for message in prepared)


@pytest.mark.asyncio
async def test_prepare_never_returns_packet_over_working_budget_when_core_fits():
    blob = "RECENT_TEXT_" + ("m" * 300)
    messages = [SystemMessage(content="s")]
    for index in range(8):
        messages.append(AIMessage(content=f"{blob}-{index}"))
    messages.append(HumanMessage(content="CURRENT_QUESTION_MUST_STAY"))
    core_tokens = count_llm_request_tokens([messages[0], messages[-1]], None, "gpt-4o")
    input_working = core_tokens + 120
    assert count_llm_request_tokens(messages, None, "gpt-4o") > input_working
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": input_working},
        compaction_enabled=True,
        compaction_max_token_threshold=50,
        compaction_keep_recent_messages=12,
        compaction_summary_max_tokens=30,
        message_trim_config=MessageTrimConfig(enabled=True, max_single_message_tokens=80, image_retain_recent=0),
    )
    isolated = AsyncMock()
    isolated.ainvoke.return_value = MagicMock(content="Summary of fat recent turns.")

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=isolated)

    assert _last_human_content(prepared) == "CURRENT_QUESTION_MUST_STAY"
    assert count_llm_request_tokens(prepared, None, "gpt-4o") <= input_working
    assert "CURRENT_QUESTION_MUST_STAY" in prepared[-1].content


@pytest.mark.asyncio
async def test_prepare_collapses_to_core_when_compaction_unavailable_and_packet_over():
    blob = "FAT_HISTORY_" + ("n" * 400)
    messages = [SystemMessage(content="system")]
    for index in range(6):
        messages.append(HumanMessage(content=f"{blob}-{index}"))
        messages.append(AIMessage(content=f"{blob}-ack-{index}"))
    messages.append(HumanMessage(content="CURRENT_QUESTION_MUST_STAY"))
    core = [messages[0], messages[-1]]
    core_tokens = count_llm_request_tokens(core, None, "gpt-4o")
    input_working = core_tokens + 40
    assert count_llm_request_tokens(messages, None, "gpt-4o") > input_working
    request = BasicLLMRequest(
        model="gpt-4o",
        extra_config={"input_working_tokens": input_working},
        compaction_enabled=False,
        message_trim_config=MessageTrimConfig(enabled=False),
    )

    prepared = await prepare_messages_for_llm(messages, request=request, isolated_llm=None)

    assert _last_human_content(prepared) == "CURRENT_QUESTION_MUST_STAY"
    assert count_llm_request_tokens(prepared, None, "gpt-4o") <= input_working
    assert count_llm_request_tokens(prepared, None, "gpt-4o") <= core_tokens
