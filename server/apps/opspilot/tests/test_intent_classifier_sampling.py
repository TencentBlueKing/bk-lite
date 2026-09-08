"""意图分类走 ChatService 内部低温 hatch，不被对话温度钉死。"""

from types import SimpleNamespace

import pytest

from apps.opspilot.metis.llm.common.llm_client_factory import INTERNAL_SAMPLING_TEMPERATURE_KEY
from apps.opspilot.models.model_provider_mgmt import LLMModel, ModelVendor
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier import INTENT_CLASSIFIER_TEMPERATURE, IntentClassifierNode

pytestmark = pytest.mark.django_db


def _vendor(**kwargs):
    data = dict(
        name="intent-vendor",
        vendor_type="openai",
        protocol_type="openai",
        api_base="https://api.example.com/v1",
        api_key="sk-test",
        enabled=True,
        team=[1],
    )
    data.update(kwargs)
    return ModelVendor.objects.create(**data)


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


def test_intent_internal_temperature_survives_chat_service_format():
    model = LLMModel.objects.create(name="intent-gpt4", vendor=_vendor(), model="gpt-4", context_window_tokens=8_000)
    params = _build_intent_params()
    params["skill_params"] = []

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(params, model)

    assert chat_kwargs["temperature"] == 0.1


def test_intent_internal_temperature_omitted_for_fixed_unit_model():
    model = LLMModel.objects.create(name="intent-kimi", vendor=_vendor(), model="kimi-k2", context_window_tokens=8_000)
    params = _build_intent_params()
    params["skill_params"] = []

    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(params, model)

    assert chat_kwargs["temperature"] is None
