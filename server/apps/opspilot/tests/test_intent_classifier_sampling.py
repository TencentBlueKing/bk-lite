"""意图分类走 ChatService 内部低温 hatch，不被对话温度钉死。"""

from types import SimpleNamespace

import pytest

from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.metis.llm.common.llm_client_factory import INTERNAL_SAMPLING_TEMPERATURE_KEY
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier import INTENT_CLASSIFIER_TEMPERATURE, IntentClassifierNode

pytestmark = pytest.mark.unit


def _llm_model(model_name="gpt-4"):
    return SimpleNamespace(
        openai_api_base="http://llm.example/v1",
        openai_api_key="key",
        model_name=model_name,
        protocol_type="openai",
        vendor_id=None,
        pk=1,
        context_window_tokens=8_000,
    )


def _chat_kwargs(**overrides):
    data = {
        "user_message": "current-question",
        "chat_history": [],
        "conversation_window_size": 10,
        "skill_prompt": "system prompt",
        "skill_params": [],
        "temperature": 0.2,
        "user_id": 1,
        "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
        "enable_suggest": False,
        "enable_query_rewrite": False,
    }
    data.update(overrides)
    return data


def _build_intent_params():
    node = IntentClassifierNode(SimpleNamespace(get_variable=lambda *_args, **_kwargs: ""))
    return node._build_llm_params(
        "intent-1",
        {"llmModel": 1, "classificationRules": ""},
        "服务器宕机了怎么办",
        {"user_id": "u1", "locale": "zh", "execution_id": "exec-1"},
        ["工单问题", "知识问答"],
    )


def test_intent_classifier_requests_internal_low_temperature():
    params = _build_intent_params()

    assert params["temperature"] == INTENT_CLASSIFIER_TEMPERATURE == 0.1
    assert params[INTERNAL_SAMPLING_TEMPERATURE_KEY] == 0.1


def test_format_chat_server_kwargs_pins_user_chat_temperature_and_ignores_slider():
    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(_chat_kwargs(temperature=0.2), _llm_model())

    assert chat_kwargs["temperature"] == 1.0
    assert INTERNAL_SAMPLING_TEMPERATURE_KEY not in chat_kwargs


def test_intent_internal_temperature_survives_chat_service_format():
    params = _build_intent_params()
    params["skill_params"] = []

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(params, _llm_model("gpt-4"))

    assert chat_kwargs["temperature"] == 0.1


def test_format_chat_server_kwargs_omits_pinned_temperature_for_fixed_unit_model():
    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(_chat_kwargs(), _llm_model("kimi-k2"))

    assert chat_kwargs["temperature"] is None


def test_intent_internal_temperature_omitted_for_fixed_unit_model():
    params = _build_intent_params()
    params["skill_params"] = []

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(params, _llm_model("gpt-5-mini"))

    assert chat_kwargs["temperature"] is None
