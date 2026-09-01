"""Chat 请求注入派生的 compaction / 单条上限；条数窗口仍先生效。"""

import pytest

from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.models.model_provider_mgmt import LLMModel, ModelVendor
from apps.opspilot.services.chat_service import ChatService

pytestmark = pytest.mark.django_db


def _vendor():
    return ModelVendor.objects.create(
        name="chat-vendor",
        vendor_type="openai",
        protocol_type="openai",
        api_base="https://api.example.com/v1",
        api_key="sk-test",
        enabled=True,
        team=[1],
    )


def _kwargs(history):
    return {
        "user_message": "current-question",
        "chat_history": history,
        "conversation_window_size": 10,
        "skill_prompt": "system prompt",
        "skill_params": [],
        "temperature": 0.2,
        "user_id": 1,
        "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
        "enable_suggest": False,
        "enable_query_rewrite": False,
    }


def test_format_chat_server_kwargs_injects_derived_budget_and_keeps_count_window():
    model = LLMModel.objects.create(name="chat-200k", vendor=_vendor(), model="gpt-4", context_window_tokens=200_000)
    history = [{"event": "user", "message": f"turn-{index}"} for index in range(11)]

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(_kwargs(history), model)

    assert len(chat_kwargs["chat_history"]) == 10
    assert chat_kwargs["chat_history"][0]["message"] == "turn-1"
    assert chat_kwargs["compaction_max_token_threshold"] == 139_500
    assert chat_kwargs["message_trim_config"]["max_single_message_tokens"] == 37_200
    assert chat_kwargs["max_output_tokens"] == 4_000
    assert chat_kwargs["extra_config"]["input_working_tokens"] == 186_000


def test_format_chat_server_kwargs_8k_window_uses_capped_output_and_smaller_trim():
    model = LLMModel.objects.create(name="chat-8k", vendor=_vendor(), model="gpt-4", context_window_tokens=8_000)
    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(_kwargs([]), model)

    assert chat_kwargs["compaction_max_token_threshold"] == 5_100
    assert chat_kwargs["message_trim_config"]["max_single_message_tokens"] == 1_360
    assert chat_kwargs["max_output_tokens"] == 800
    assert chat_kwargs["extra_config"]["input_working_tokens"] == 6_800
