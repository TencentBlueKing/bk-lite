"""LLM 调用前 trim + compact；裁无可裁时明确失败且不截断本轮问题。"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.prepare_llm_context import LLMContextWindowExceeded, prepare_messages_for_llm
from apps.opspilot.metis.llm.chain.token_utils import count_message_tokens


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
