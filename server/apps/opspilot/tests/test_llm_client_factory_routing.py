"""LLMClientFactory：协议路由、thinking 参数、隔离客户端。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory

pytestmark = pytest.mark.unit


def _request(**kwargs):
    data = dict(
        openai_api_base="http://llm.local",
        openai_api_key="k",
        model="gpt-4o",
        protocol_type="openai",
        temperature=0.2,
        extra_config={"show_think": True},
    )
    data.update(kwargs)
    return BasicLLMRequest(**data)


def test_create_client_openai_qwen_deepseek_and_isolated(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )

    created = {}

    class FakeChat:
        def __init__(self, **kwargs):
            created["kwargs"] = kwargs
            self.extra_body = None
            self.callbacks = "keep"

    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI", FakeChat)
    qwen = LLMClientFactory.create_client(_request(model="Qwen2.5-72B"), isolated=True)
    assert qwen.callbacks is None
    assert qwen.extra_body["enable_thinking"] is True

    deepseek = LLMClientFactory.create_client(_request(model="deepseek-chat", extra_config={"show_think": False}))
    assert deepseek.extra_body["thinking"] == {"type": "disabled"}


def test_create_client_anthropic_and_compatible(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )
    anthro = MagicMock(name="ChatAnthropic")
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic", anthro)
    LLMClientFactory.create_client(_request(protocol_type="anthropic", model="claude-3", openai_api_base="https://api.openai.com"))
    anthro.assert_called_once()
    kwargs = anthro.call_args.kwargs
    assert kwargs["anthropic_api_url"] == "https://api.anthropic.com"
    assert kwargs["model"] == "claude-3"

    compat = MagicMock(name="Compat")
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.AnthropicCompatibleChatClient",
        compat,
    )
    LLMClientFactory.create_client(_request(protocol_type="anthropic", vendor_type="deepseek", model="deepseek-v3"))
    compat.assert_called_once()
    assert compat.call_args.kwargs["vendor_type"] == "deepseek"


def test_create_isolated_clients_and_invoke(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )
    openai_cls = MagicMock(name="OpenAI")
    anthro_cls = MagicMock(name="Anthropic")
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI", openai_cls)
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.anthropic.Anthropic", anthro_cls)

    openai_client = LLMClientFactory.create_isolated_client(_request())
    assert openai_client is openai_cls.return_value
    openai_cls.assert_called_once()
    assert openai_cls.call_args.kwargs["base_url"] == "http://llm.local"

    anthro_client = LLMClientFactory.create_isolated_client(_request(protocol_type="anthropic", openai_api_base=""))
    assert anthro_client is anthro_cls.return_value
    assert anthro_cls.call_args.kwargs["base_url"] == "https://api.anthropic.com"

    openai_cls.return_value.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="rewritten"))]
    )
    text = LLMClientFactory.invoke_isolated(_request(), [HumanMessage(content="hi")])
    assert text == "rewritten"
    payload = openai_cls.return_value.chat.completions.create.call_args.kwargs
    assert payload["messages"][0] == {"role": "user", "content": "hi"}


def test_create_client_gemma_and_openai_without_extra_body(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )

    class FakeChat:
        def __init__(self, **kwargs):
            self.extra_body = None
            self.callbacks = "keep"

    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.ChatOpenAI", FakeChat)
    gemma = LLMClientFactory.create_client(_request(model="gemma-4-27b", extra_config={"show_think": False}))
    assert gemma.extra_body["chat_template_kwargs"] == {"enable_thinking": False}
    assert gemma.callbacks == "keep"


def test_create_client_anthropic_deepseek_thinking(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )
    anthro = MagicMock(name="ChatAnthropic")
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.ChatAnthropic", anthro)
    LLMClientFactory.create_client(_request(protocol_type="anthropic", model="deepseek-chat", extra_config={"show_think": False}))
    kwargs = anthro.call_args.kwargs
    assert kwargs["model_kwargs"] == {"thinking": {"type": "disabled"}}
    assert kwargs["anthropic_api_url"] == "http://llm.local"


def test_invoke_isolated_openai_roles_and_model_extras(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )
    openai_cls = MagicMock(name="OpenAI")
    openai_cls.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.OpenAI", openai_cls)

    other = SimpleNamespace(type="assistant", content="prev")
    text = LLMClientFactory.invoke_isolated(
        _request(model="Qwen2.5"),
        [HumanMessage(content="q"), {"role": "user", "content": "dict"}, other],
    )
    assert text == "ok"
    kwargs = openai_cls.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["messages"] == [
        {"role": "user", "content": "q"},
        {"role": "user", "content": "dict"},
        {"role": "assistant", "content": "prev"},
    ]
    assert kwargs["extra_body"] == {
        "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    LLMClientFactory.invoke_isolated(_request(model="deepseek-v3"), [HumanMessage(content="x")])
    assert openai_cls.return_value.chat.completions.create.call_args.kwargs["extra_body"] == {
        "enable_thinking": False,
        "thinking": {"type": "disabled"},
    }
    LLMClientFactory.invoke_isolated(_request(model="gemma-3"), [HumanMessage(content="x")])
    assert openai_cls.return_value.chat.completions.create.call_args.kwargs["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_invoke_isolated_anthropic_system_and_plain_messages(monkeypatch):
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.SSRFValidator.validate_llm_endpoint",
        lambda *a, **k: None,
    )
    anthro_cls = MagicMock(name="Anthropic")
    anthro_cls.return_value.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text="ans")])
    monkeypatch.setattr("apps.opspilot.metis.llm.common.llm_client_factory.anthropic.Anthropic", anthro_cls)
    text = LLMClientFactory.invoke_isolated(
        _request(protocol_type="anthropic", openai_api_base="https://api.openai.com"),
        [
            {"role": "system", "content": "sys"},
            HumanMessage(content="hi"),
            SimpleNamespace(type="system", content="sys2"),
            SimpleNamespace(type="assistant", content="prev"),
            {"role": "user", "content": "again"},
        ],
    )
    assert text == "ans"
    kwargs = anthro_cls.return_value.messages.create.call_args.kwargs
    assert kwargs["system"] == "sys2"
    assert kwargs["max_tokens"] == 4096
    assert kwargs["messages"][0] == {"role": "user", "content": "hi"}
    assert anthro_cls.call_args.kwargs["base_url"] == "https://api.anthropic.com"
