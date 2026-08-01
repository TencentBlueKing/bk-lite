"""Anthropic 兼容适配器与 LLM 工厂的公共契约测试。

网络客户端是外部边界；测试保留真实的消息转换、工具绑定、协议选择和请求参数组装。
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common import anthropic_compatible_adapter as adapter
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory


pytestmark = pytest.mark.unit


class SearchArgs(BaseModel):
    query: str


class SearchTool:
    name = "search"
    description = "Search public documents"
    args_schema = SearchArgs


class LegacySchema:
    def schema(self):
        return {"type": "object", "properties": {"value": {"type": "integer"}}}


class LegacyTool:
    name = "legacy"
    description = "Legacy schema"
    args_schema = LegacySchema()


def test_anthropic_url_headers_and_tool_schema_are_normalized():
    assert adapter.normalize_messages_url("") == "https://api.anthropic.com/v1/messages"
    assert adapter.normalize_messages_url("https://llm.example/") == "https://llm.example/v1/messages"
    assert adapter.build_anthropic_headers("secret") == {
        "x-api-key": "secret",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    definitions = adapter.build_tool_definitions([SearchTool(), LegacyTool(), SimpleNamespace()])
    assert definitions[0]["input_schema"]["required"] == ["query"]
    assert definitions[1]["input_schema"]["properties"]["value"]["type"] == "integer"
    assert definitions[2]["input_schema"] == {"type": "object", "properties": {}}


def test_anthropic_payload_preserves_system_tools_and_tool_results():
    payload = adapter.build_messages_payload(
        model="claude-compatible",
        messages=[
            SystemMessage(content="Be exact"),
            HumanMessage(content="find host"),
            AIMessage(
                content="checking",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "search",
                        "args": {"query": "host"},
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content="host-01", tool_call_id="call-1"),
            HumanMessage(content="summarize"),
        ],
        temperature=0.2,
        max_tokens=128,
        tools=[SearchTool()],
        tool_choice="search",
    )

    assert payload["system"] == "Be exact"
    assert payload["tool_choice"] == {"type": "tool", "name": "search"}
    assert payload["tools"][0]["name"] == "search"
    assert payload["messages"] == [
        {"role": "user", "content": "find host"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "checking"},
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "search",
                    "input": {"query": "host"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "content": "host-01",
                }
            ],
        },
        {"role": "user", "content": "summarize"},
    ]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("auto", {"type": "auto"}),
        ("any", {"type": "any"}),
        ("required", {"type": "required"}),
        ({"type": "tool", "name": "search"}, {"type": "tool", "name": "search"}),
    ],
)
def test_anthropic_tool_choice_object_is_protocol_compliant(choice, expected):
    assert adapter._normalize_tool_choice_to_object(choice) == expected


def test_anthropic_payload_omits_disabled_optional_fields():
    payload = adapter.build_messages_payload(
        model="m",
        messages=[AIMessage(content="answer")],
        temperature=0,
        tools=[],
        tool_choice="none",
    )
    assert payload["messages"] == [
        {"role": "assistant", "content": [{"type": "text", "text": "answer"}]}
    ]
    assert "system" not in payload
    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_anthropic_connection_validation_posts_minimal_request(monkeypatch):
    response = SimpleNamespace(status_code=204, text="")
    post = pytest.MonkeyPatch()
    calls = {}

    def fake_post(url, **kwargs):
        calls.update(url=url, **kwargs)
        return response

    monkeypatch.setattr(adapter, "safe_post_llm_endpoint", fake_post)
    adapter.AnthropicCompatibleAdapter.validate_minimal_connection(
        "https://llm.example/", "key", "model-a"
    )
    assert calls == {
        "url": "https://llm.example/v1/messages",
        "headers": adapter.build_anthropic_headers("key"),
        "json": {
            "model": "model-a",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        },
        "timeout": 15,
    }
    post.undo()


@pytest.mark.parametrize(
    ("status", "text", "message"),
    [
        (401, "unauthorized", "API Key 无效"),
        (429, "rate limited", "API 连接失败: rate limited"),
        (503, "", "API 连接失败: HTTP 503"),
    ],
)
def test_anthropic_connection_errors_are_actionable(status, text, message):
    response = SimpleNamespace(status_code=status, text=text)
    with pytest.raises(ValueError, match=message):
        adapter.AnthropicCompatibleAdapter._raise_for_error(response)


def test_anthropic_chat_client_generates_text_and_tool_calls(monkeypatch):
    response = SimpleNamespace(
        status_code=200,
        text="",
        json=lambda: {
            "content": [
                {"type": "text", "text": "found "},
                {
                    "type": "tool_use",
                    "id": "call-9",
                    "name": "search",
                    "input": {"query": "cpu"},
                },
                {"type": "text", "text": "one"},
            ]
        },
    )
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return response

    monkeypatch.setattr(adapter, "safe_post_llm_endpoint", fake_post)
    client = adapter.AnthropicCompatibleChatClient(
        model="m",
        api_key="k",
        api_base="https://llm.example",
        temperature=0.1,
        timeout=9,
    ).bind_tools([SearchTool()], tool_choice="auto")

    result = client._generate([HumanMessage(content="inspect")])
    message = result.generations[0].message
    assert client._llm_type == "anthropic-compatible"
    assert message.content == "found one"
    assert message.tool_calls == [
        {
            "name": "search",
            "args": {"query": "cpu"},
            "id": "call-9",
            "type": "tool_call",
        }
    ]
    assert captured["timeout"] == 9
    assert captured["json"]["tool_choice"] == {"type": "auto"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 300.0), ("bad", 300.0), (0, 1.0), ("2.5", 2.5)],
)
def test_llm_factory_timeout_has_stable_floor_and_fallback(monkeypatch, raw, expected):
    monkeypatch.setenv("LLM_INVOKE_TIMEOUT", "300")
    request = BasicLLMRequest(extra_config={} if raw is None else {"timeout": raw})
    assert LLMClientFactory._resolve_timeout(request) == expected


@pytest.mark.parametrize(
    ("protocol", "capability", "creator"),
    [
        ("openai", False, "_create_openai_client"),
        ("anthropic", False, "_create_anthropic_client"),
        ("anthropic", True, "_create_anthropic_compatible_client"),
    ],
)
def test_llm_factory_routes_public_client_creation(
    monkeypatch, protocol, capability, creator
):
    request = BasicLLMRequest(protocol_type=protocol, vendor_type="vendor")
    created = SimpleNamespace(callbacks=["tracked"])
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.common.llm_client_factory.build_anthropic_runtime_capabilities",
        lambda *_: SimpleNamespace(use_anthropic_compatible_adapter=capability),
    )
    selected = monkeypatch.setattr(
        LLMClientFactory, creator, lambda *_args: created
    )

    result = LLMClientFactory.create_client(
        request, disable_stream=True, isolated=True, timeout=12
    )
    assert result is created
    assert result.callbacks is None
    assert selected is None


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_llm_factory_public_isolated_invocation_routes_protocol(monkeypatch, protocol):
    request = BasicLLMRequest(protocol_type=protocol)
    method = (
        "_invoke_isolated_anthropic"
        if protocol == "anthropic"
        else "_invoke_isolated_openai"
    )
    monkeypatch.setattr(LLMClientFactory, method, lambda _request, messages: messages[0])
    assert LLMClientFactory.invoke_isolated(request, ["answer"]) == "answer"


def test_isolated_openai_invocation_converts_mixed_messages(monkeypatch):
    create = pytest.MonkeyPatch()
    calls = {}
    completion = SimpleNamespace(
        create=lambda **kwargs: (
            calls.update(kwargs)
            or SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
            )
        )
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
    monkeypatch.setattr(
        LLMClientFactory, "_create_isolated_openai_client", lambda _request: client
    )
    request = BasicLLMRequest(model="qwen3", temperature=0.3)
    custom = SimpleNamespace(type="assistant", content="prior")

    assert LLMClientFactory._invoke_isolated_openai(
        request,
        [HumanMessage(content="hello"), {"role": "user", "content": "world"}, custom],
    ) == "ok"
    assert calls["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
        {"role": "assistant", "content": "prior"},
    ]
    assert calls["extra_body"] == {"enable_thinking": False}
    create.undo()


def test_isolated_anthropic_invocation_separates_system_message(monkeypatch):
    calls = {}
    messages_api = SimpleNamespace(
        create=lambda **kwargs: (
            calls.update(kwargs)
            or SimpleNamespace(content=[SimpleNamespace(text="done")])
        )
    )
    client = SimpleNamespace(messages=messages_api)
    monkeypatch.setattr(
        LLMClientFactory,
        "_create_isolated_anthropic_client",
        lambda _request: client,
    )
    request = BasicLLMRequest(
        protocol_type="anthropic", model="claude", temperature=0.4
    )
    custom = SimpleNamespace(type="assistant", content="previous")

    assert LLMClientFactory._invoke_isolated_anthropic(
        request,
        [
            {"role": "system", "content": "Be concise"},
            HumanMessage(content="hello"),
            custom,
        ],
    ) == "done"
    assert calls == {
        "model": "claude",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "previous"},
        ],
        "temperature": 0.4,
        "max_tokens": 4096,
        "system": "Be concise",
    }
