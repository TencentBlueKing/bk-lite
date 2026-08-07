"""
Anthropic Compatible Adapter

Shared helpers for validating connectivity to Anthropic-protocol endpoints
(native Anthropic API and Anthropic-compatible providers such as DeepSeek).
"""

from typing import Any, List, Optional

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from apps.core.utils.safe_requests import safe_post_llm_endpoint

_ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_INVALID_API_KEY_ERROR = "API Key 无效"


def normalize_anthropic_compatible_api_base(api_base: str, vendor_type: str = "") -> str:
    """Normalize vendor Anthropic-compatible base URLs.

    DeepSeek 官方 Anthropic 兼容入口为 ``https://api.deepseek.com/anthropic``。
    若配置成 OpenAI 根地址（``https://api.deepseek.com`` / ``.../v1``），
    再拼 ``/v1/messages`` 会打到错误路径，表现为模型“收到空消息”。
    """
    base = (api_base or "").strip().rstrip("/")
    if not base or base == "https://api.openai.com":
        return "https://api.anthropic.com"
    vendor = (vendor_type or "").strip().casefold()
    if vendor == "deepseek":
        if base.endswith("/anthropic"):
            return base
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        if base.rstrip("/") == "https://api.deepseek.com":
            return "https://api.deepseek.com/anthropic"
    return base


def normalize_messages_url(api_base: str) -> str:
    """Return the /v1/messages URL for the given api_base.

    Defaults to the official Anthropic base when api_base is empty.
    """
    base = (api_base or _ANTHROPIC_DEFAULT_BASE).rstrip("/")
    return f"{base}/v1/messages"


def build_anthropic_headers(api_key: str) -> dict:
    """Build the HTTP headers required by the Anthropic messages API."""
    return {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _message_role(message) -> str:
    return getattr(message, "type", getattr(message, "role", "user"))


def _schema_to_parameters(args_schema) -> dict:
    if not args_schema:
        return {"type": "object", "properties": {}}
    if hasattr(args_schema, "model_json_schema"):
        return args_schema.model_json_schema()
    if hasattr(args_schema, "schema"):
        return args_schema.schema()
    return {"type": "object", "properties": {}}


def build_tool_definitions(tools: list) -> list:
    definitions = []
    for tool in tools or []:
        definitions.append(
            {
                "name": getattr(tool, "name", ""),
                "description": getattr(tool, "description", ""),
                "input_schema": _schema_to_parameters(getattr(tool, "args_schema", None)),
            }
        )
    return definitions


def build_messages_payload(
    *,
    model: str,
    messages: list,
    temperature: float,
    max_tokens: int = 4096,
    tools: list | None = None,
    tool_choice: str | None = None,
) -> dict:
    system_message = None
    anthropic_messages = []
    pending_tool_results = []

    def flush_tool_results():
        nonlocal pending_tool_results
        if pending_tool_results:
            anthropic_messages.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for message in messages:
        role = _message_role(message)
        content = getattr(message, "content", "")
        if role == "system":
            system_message = content
            continue
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": getattr(message, "tool_call_id", ""),
                    "content": content,
                }
            )
            continue
        flush_tool_results()
        mapped_role = "assistant" if role in {"assistant", "ai"} else "user"
        if mapped_role == "assistant":
            assistant_content = []
            if content:
                assistant_content.append({"type": "text", "text": content})
            for tool_call in getattr(message, "tool_calls", []) or []:
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.get("id", ""),
                        "name": tool_call.get("name", ""),
                        "input": tool_call.get("args", {}),
                    }
                )
            anthropic_messages.append({"role": mapped_role, "content": assistant_content or content})
            continue
        anthropic_messages.append({"role": mapped_role, "content": content})
    flush_tool_results()

    payload = {
        "model": model,
        "messages": anthropic_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if system_message:
        payload["system"] = system_message
    if tools:
        payload["tools"] = build_tool_definitions(tools)
    if tool_choice and tool_choice != "none":
        payload["tool_choice"] = _normalize_tool_choice_to_object(tool_choice)
    return payload


def _normalize_tool_choice_to_object(tool_choice: str | dict) -> dict:
    """Convert tool_choice to Anthropic object format.

    Anthropic protocol requires {"type": "auto"} not plain string "auto".
    Specific tool: {"type": "tool", "name": "tool_name"}
    Note: "none" should be handled by the caller (omit tool_choice field entirely).
    """
    if isinstance(tool_choice, dict):
        return tool_choice
    if tool_choice in ("auto", "any", "required"):
        return {"type": tool_choice}
    # Specific tool name
    return {"type": "tool", "name": tool_choice}


class AnthropicCompatibleAdapter:
    """Adapter for Anthropic-protocol endpoints (native and compatible)."""

    @staticmethod
    def validate_minimal_connection(api_base: str, api_key: str, model: str) -> None:
        """POST a minimal request to verify the endpoint is reachable.

        Raises:
            ValueError: if the API key is invalid or the request fails.
        """
        url = normalize_messages_url(api_base)
        headers = build_anthropic_headers(api_key)
        response = safe_post_llm_endpoint(
            url,
            headers=headers,
            json={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=15,
        )
        AnthropicCompatibleAdapter._raise_for_error(response)

    @staticmethod
    def _raise_for_error(response) -> None:
        """Raise ValueError for non-2xx responses."""
        if response.status_code == 401:
            raise ValueError(ANTHROPIC_INVALID_API_KEY_ERROR)
        if response.status_code >= 400:
            error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            raise ValueError(f"API 连接失败: {error_msg}")


class AnthropicCompatibleChatClient(BaseChatModel):
    """Thin runtime client for Anthropic-compatible vendors.

    Inherits BaseChatModel so LangGraph astream_events emits on_chat_model_stream
    events, enabling proper frontend text streaming.
    """

    model: str
    api_key: str
    api_base: str
    temperature: float
    max_tokens: int = 4096
    disable_streaming: bool = False
    timeout: int = 15
    vendor_type: str = ""
    bound_tools: List[Any] = []
    bound_tool_choice: Optional[str] = None
    thinking_enabled: Optional[bool] = None

    @property
    def _llm_type(self) -> str:
        return "anthropic-compatible"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = build_messages_payload(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=self.bound_tools,
            tool_choice=self.bound_tool_choice,
        )
        if self.thinking_enabled is not None and "deepseek" in (self.vendor_type or self.model or "").casefold():
            payload["thinking"] = {"type": "enabled" if self.thinking_enabled else "disabled"}
        response = safe_post_llm_endpoint(
            normalize_messages_url(self.api_base),
            headers=build_anthropic_headers(self.api_key),
            json=payload,
            timeout=self.timeout,
        )
        AnthropicCompatibleAdapter._raise_for_error(response)
        ai_message = _build_ai_message(response.json())
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(
            update={
                "bound_tools": list(tools or []),
                "bound_tool_choice": kwargs.get("tool_choice"),
            }
        )


def _build_ai_message(payload: dict) -> AIMessage:
    content_parts = payload.get("content", []) if isinstance(payload, dict) else []
    text_parts = []
    tool_calls = []
    for item in content_parts:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
        elif item.get("type") == "tool_use":
            tool_calls.append(
                {
                    "name": item.get("name", ""),
                    "args": item.get("input", {}),
                    "id": item.get("id", ""),
                    "type": "tool_call",
                }
            )
    return AIMessage(content="".join(text_parts), tool_calls=tool_calls)
