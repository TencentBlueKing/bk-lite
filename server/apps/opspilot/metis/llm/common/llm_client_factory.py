"""LLM客户端工厂类,用于创建不同用途的LLM客户端"""

import os
from typing import Union

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI, omit

from apps.core.utils.ssrf_validator import SSRFValidator
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.anthropic_capabilities import build_anthropic_runtime_capabilities
from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import AnthropicCompatibleChatClient, normalize_anthropic_compatible_api_base

# Vendor test uses requests GET /models; chat uses the OpenAI Python SDK
# (User-Agent OpenAI/Python + X-Stainless-*). Some reverse proxies return
# 403 "Your request was blocked" for the SDK while curl/Postman still work.
_OPENAI_COMPAT_USER_AGENT = "curl/8.7.1"
_OPENAI_SDK_STAINLESS_HEADER_NAMES = (
    "X-Stainless-Lang",
    "X-Stainless-Package-Version",
    "X-Stainless-OS",
    "X-Stainless-Arch",
    "X-Stainless-Runtime",
    "X-Stainless-Runtime-Version",
    "X-Stainless-Async",
)


def openai_compat_user_agent_headers() -> dict[str, str]:
    """Public ChatOpenAI headers. Values must be str; langchain rejects omit."""
    return {"User-Agent": _OPENAI_COMPAT_USER_AGENT}


def openai_compat_sdk_headers() -> dict:
    """Native OpenAI() headers: curl UA and drop SDK fingerprint headers."""
    return {
        "User-Agent": _OPENAI_COMPAT_USER_AGENT,
        **{name: omit for name in _OPENAI_SDK_STAINLESS_HEADER_NAMES},
    }


def _attach_openai_compat_sdk_headers(llm) -> None:
    """ChatOpenAI cannot take omit in default_headers; patch the wrapped clients."""
    headers = openai_compat_sdk_headers()
    for attr in ("root_client", "root_async_client"):
        client = getattr(llm, attr, None)
        if client is None or not hasattr(client, "_custom_headers"):
            continue
        client._custom_headers = {**client._custom_headers, **headers}


def _build_openai_thinking_extra_body(model: str, show_think: bool) -> dict:
    """Build OpenAI-compatible ``extra_body`` toggles for thinking/reasoning mode.

    DeepSeek V4（含 ``deepseek-v4-flash``）默认开启 thinking。官方 API 用
    ``thinking.type``，DashScope 等兼容网关用 ``enable_thinking``；两边都写，
    避免 ``show_think=false`` 时仍默认思考并把旁白打进正文。

    Qwen3 同类：DashScope 认顶层 ``enable_thinking``，vLLM / 本地 OpenAI 兼容
    服务只认 ``chat_template_kwargs.enable_thinking``。只写顶层字段会被静默忽略，
    思考占满 ``max_tokens`` 后 ``content`` 为空。
    """
    model_lower = (model or "").lower()
    if "qwen" in model_lower:
        return {
            "enable_thinking": show_think,
            "chat_template_kwargs": {"enable_thinking": show_think},
        }
    if "deepseek" in model_lower:
        return {
            "thinking": {"type": "enabled" if show_think else "disabled"},
            "enable_thinking": show_think,
        }
    if "gemma" in model_lower:
        return {"chat_template_kwargs": {"enable_thinking": show_think}}
    return {}


def _coerce_optional_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_reasoning_tokens(usage):
    """Read provider reasoning-token counts without dumping usage objects."""
    if usage is None:
        return None
    details = usage.get("completion_tokens_details") if isinstance(usage, dict) else getattr(usage, "completion_tokens_details", None)
    if isinstance(details, dict):
        reasoning = _coerce_optional_int(details.get("reasoning_tokens"))
        if reasoning is not None:
            return reasoning
    elif details is not None:
        reasoning = _coerce_optional_int(getattr(details, "reasoning_tokens", None))
        if reasoning is not None:
            return reasoning
    if isinstance(usage, dict):
        return _coerce_optional_int(usage.get("reasoning_tokens"))
    return _coerce_optional_int(getattr(usage, "reasoning_tokens", None))


def _isolated_usage_dict(usage) -> dict:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    else:
        prompt_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None) or 0
        completion_tokens = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None) or 0
    data = {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
    }
    reasoning_tokens = _extract_reasoning_tokens(usage)
    if reasoning_tokens is not None:
        data["reasoning_tokens"] = reasoning_tokens
    return data


def _message_has_reasoning_content(message) -> bool:
    if message is None:
        return False
    for attr in ("reasoning_content", "reasoning"):
        raw = getattr(message, attr, None)
        if isinstance(raw, str) and raw.strip():
            return True
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        for key in ("reasoning_content", "reasoning"):
            raw = extra.get(key)
            if isinstance(raw, str) and raw.strip():
                return True
    return False


def _thinking_extra_body_flags(thinking_body):
    body = thinking_body or {}
    enable = body.get("enable_thinking") if "enable_thinking" in body else None
    if enable is not None:
        enable = bool(enable)
    template = body.get("chat_template_kwargs")
    template_enable = None
    if isinstance(template, dict) and "enable_thinking" in template:
        template_enable = bool(template.get("enable_thinking"))
    return enable, template_enable


def _attach_isolated_openai_result(request, *, thinking_body, finish_reason, usage, message, text):
    thinking_enable, thinking_template_enable = _thinking_extra_body_flags(thinking_body)
    extra = {
        **(request.extra_config or {}),
        "_isolated_finish_reason": finish_reason,
        "_isolated_output_truncated": str(finish_reason or "").casefold() in {"length", "max_tokens", "max_output_tokens", "token_limit"},
        "_isolated_thinking_enable": thinking_enable,
        "_isolated_thinking_template_enable": thinking_template_enable,
        "_isolated_has_reasoning_content": _message_has_reasoning_content(message),
        "_isolated_content_chars": len(text or ""),
    }
    usage_dict = _isolated_usage_dict(usage)
    if usage_dict:
        extra["_isolated_usage"] = usage_dict
    request.extra_config = extra


def _normalize_message_content(content) -> str:
    """Normalize provider message content into plain text.

    OpenAI-compatible gateways may return ``None``, a bare string, or a list of
    content parts. Anthropic returns a list of typed blocks. Callers that expect
    a string (Wiki build JSON parse) must not receive ``None``.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
                continue
            text = getattr(item, "text", None)
            if text:
                parts.append(str(text))
        return "\n".join(part for part in parts if part)
    return str(content)


# 部分推理/新一代模型网关只接受 temperature=1。
_FIXED_UNIT_TEMPERATURE_PREFIXES = ("gpt-5", "o1", "o3", "o4-mini", "kimi", "moonshot", "k3")


def _normalize_llm_model_id(model_name: str) -> str:
    name = str(model_name or "").strip().lower()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return name


def resolve_gateway_temperature(model_name: str, requested: float, vendor_type: str = "") -> float:
    """Keep the requested temperature unless the gateway only accepts 1."""
    name = _normalize_llm_model_id(model_name)
    vendor = str(vendor_type or "").strip().lower()
    if vendor in {"kimi", "moonshot"}:
        return 1.0
    for prefix in _FIXED_UNIT_TEMPERATURE_PREFIXES:
        if name == prefix or name.startswith(f"{prefix}-") or name.startswith(f"{prefix}."):
            return 1.0
    return requested


def _request_temperature(request: BasicLLMRequest) -> float:
    return resolve_gateway_temperature(request.model, request.temperature, getattr(request, "vendor_type", ""))


def _is_unsupported_response_format_error(exc) -> bool:
    """Detect providers/gateways that reject OpenAI response_format."""
    text = str(exc or "").casefold()
    needles = (
        "response_format",
        "response format",
        "json_object",
        "json mode",
        "unsupported parameter",
        "unknown parameter",
        "not supported",
    )
    return any(needle in text for needle in needles)


class LLMClientFactory:
    """LLM客户端工厂"""

    @staticmethod
    def _resolve_timeout(request: BasicLLMRequest = None, timeout=None, default: float = 300.0) -> float:
        """解析 LLM 客户端超时，允许请求级 extra_config 覆盖全局环境变量。"""
        if timeout is not None:
            raw_timeout = timeout
        else:
            extra_config = request.extra_config if request and request.extra_config else {}
            raw_timeout = os.getenv("LLM_INVOKE_TIMEOUT", "300")
            for config_key in ("timeout", "request_timeout", "llm_timeout"):
                configured_timeout = extra_config.get(config_key)
                if configured_timeout is not None:
                    raw_timeout = configured_timeout
                    break
        try:
            resolved_timeout = float(raw_timeout)
        except (TypeError, ValueError):
            resolved_timeout = default
        return max(resolved_timeout, 1.0)

    @staticmethod
    def create_client(request: BasicLLMRequest, disable_stream=False, isolated=False, timeout=None) -> BaseChatModel:
        """
        创建LLM客户端

        Args:
            request: LLM请求对象
            disable_stream: 是否禁用流式输出
            isolated: 是否创建独立客户端(不被LangGraph跟踪),用于内部调用如问题改写
            timeout: 可选，单次 LLM 调用超时（秒）；不传时使用 LLM_INVOKE_TIMEOUT，默认 300 秒

        Returns:
            BaseChatModel客户端实例 (ChatOpenAI 或 ChatAnthropic)
        """
        timeout = LLMClientFactory._resolve_timeout(request, timeout=timeout)
        capabilities = build_anthropic_runtime_capabilities(
            getattr(request, "vendor_type", ""),
            request.protocol_type,
        )
        if capabilities.use_anthropic_compatible_adapter:
            llm = LLMClientFactory._create_anthropic_compatible_client(request, disable_stream, timeout)
        elif request.protocol_type == "anthropic":
            llm = LLMClientFactory._create_anthropic_client(request, disable_stream, timeout)
        else:
            llm = LLMClientFactory._create_openai_client(request, disable_stream, timeout)

        # 如果需要隔离,则禁用callbacks以避免被LangGraph捕获
        if isolated:
            llm.callbacks = None

        return llm

    @staticmethod
    def _create_openai_client(request: BasicLLMRequest, disable_stream: bool, timeout: int = None) -> ChatOpenAI:
        """创建 OpenAI 兼容客户端"""
        # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
        base_url = request.openai_api_base
        if base_url:
            SSRFValidator.validate_llm_endpoint(base_url)

        llm = ChatOpenAI(
            model=request.model,
            base_url=base_url,
            api_key=request.openai_api_key,
            temperature=_request_temperature(request),
            max_tokens=request.max_output_tokens or None,
            disable_streaming=disable_stream,
            timeout=LLMClientFactory._resolve_timeout(request, timeout=timeout),
            default_headers=openai_compat_user_agent_headers(),
        )
        _attach_openai_compat_sdk_headers(llm)

        if llm.extra_body is None:
            llm.extra_body = {}

        show_think = bool((request.extra_config or {}).get("show_think", True))
        llm.extra_body.update(_build_openai_thinking_extra_body(request.model, show_think))

        return llm

    @staticmethod
    def _create_anthropic_client(request: BasicLLMRequest, disable_stream: bool, timeout: int = None) -> ChatAnthropic:
        """创建 Anthropic 客户端"""
        # Anthropic API base URL 处理
        base_url = request.openai_api_base
        if not base_url or base_url == "https://api.openai.com":
            base_url = "https://api.anthropic.com"

        # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
        SSRFValidator.validate_llm_endpoint(base_url)

        # 处理 thinking 模式
        show_think = bool((request.extra_config or {}).get("show_think", True))
        model_kwargs = {}

        # DeepSeek Anthropic API 使用与 OpenAI 相同的 thinking 参数格式
        model_lower = request.model.lower()
        if "deepseek" in model_lower:
            thinking_type = "enabled" if show_think else "disabled"
            model_kwargs["thinking"] = {"type": thinking_type}

        llm = ChatAnthropic(
            model=request.model,
            anthropic_api_url=base_url,
            api_key=request.openai_api_key,
            temperature=_request_temperature(request),
            max_tokens=request.max_output_tokens or 4096,
            disable_streaming=disable_stream,
            timeout=LLMClientFactory._resolve_timeout(request, timeout=timeout),
            model_kwargs=model_kwargs if model_kwargs else None,
        )

        return llm

    @staticmethod
    def _create_anthropic_compatible_client(request: BasicLLMRequest, disable_stream: bool, timeout: int = None) -> AnthropicCompatibleChatClient:
        """Create a thin runtime client for Anthropic-compatible vendors."""
        capabilities = build_anthropic_runtime_capabilities(
            getattr(request, "vendor_type", ""),
            request.protocol_type,
        )
        base_url = request.openai_api_base
        if capabilities.requires_normalized_base_url:
            base_url = normalize_anthropic_compatible_api_base(
                base_url,
                getattr(request, "vendor_type", ""),
            )
        elif not base_url or base_url == "https://api.openai.com":
            base_url = "https://api.anthropic.com"

        SSRFValidator.validate_llm_endpoint(base_url)

        show_think = bool((request.extra_config or {}).get("show_think", True))

        return AnthropicCompatibleChatClient(
            model=request.model,
            api_key=request.openai_api_key,
            api_base=base_url,
            temperature=_request_temperature(request),
            max_tokens=request.max_output_tokens or 4096,
            disable_streaming=disable_stream,
            timeout=LLMClientFactory._resolve_timeout(request, timeout=timeout),
            vendor_type=getattr(request, "vendor_type", ""),
            thinking_enabled=show_think,
        )

    @staticmethod
    def create_isolated_client(request: BasicLLMRequest) -> Union[OpenAI, anthropic.Anthropic]:
        """
        创建独立的原生客户端,完全绕过LangChain/LangGraph追踪
        适用于内部调用场景,如问题改写、知识路由等

        Args:
            request: LLM请求对象

        Returns:
            原生客户端实例 (OpenAI 或 Anthropic)
        """
        if request.protocol_type == "anthropic":
            return LLMClientFactory._create_isolated_anthropic_client(request)
        else:
            return LLMClientFactory._create_isolated_openai_client(request)

    @staticmethod
    def _create_isolated_openai_client(request: BasicLLMRequest) -> OpenAI:
        """创建独立的原生 OpenAI 客户端"""
        kwargs = {
            "api_key": request.openai_api_key,
            "timeout": LLMClientFactory._resolve_timeout(request),
            "default_headers": openai_compat_sdk_headers(),
        }
        if request.openai_api_base:
            # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
            SSRFValidator.validate_llm_endpoint(request.openai_api_base)
            kwargs["base_url"] = request.openai_api_base
        return OpenAI(**kwargs)

    @staticmethod
    def _create_isolated_anthropic_client(request: BasicLLMRequest) -> anthropic.Anthropic:
        """创建独立的原生 Anthropic 客户端"""
        capabilities = build_anthropic_runtime_capabilities(
            getattr(request, "vendor_type", ""),
            request.protocol_type,
        )
        base_url = request.openai_api_base
        if capabilities.requires_normalized_base_url:
            base_url = normalize_anthropic_compatible_api_base(
                base_url,
                getattr(request, "vendor_type", ""),
            )
        elif not base_url or base_url == "https://api.openai.com":
            base_url = "https://api.anthropic.com"

        # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
        SSRFValidator.validate_llm_endpoint(base_url)

        return anthropic.Anthropic(
            api_key=request.openai_api_key,
            base_url=base_url,
            timeout=LLMClientFactory._resolve_timeout(request),
        )

    @staticmethod
    def invoke_isolated(request: BasicLLMRequest, messages: list) -> str:
        """
        使用独立客户端调用LLM,不会被LangGraph捕获

        Args:
            request: LLM请求对象
            messages: 消息列表,格式为 [HumanMessage(...)] 或 [{"role": "user", "content": "..."}]

        Returns:
            LLM响应内容字符串
        """
        if request.protocol_type == "anthropic":
            return LLMClientFactory._invoke_isolated_anthropic(request, messages)
        else:
            return LLMClientFactory._invoke_isolated_openai(request, messages)

    @staticmethod
    def _invoke_isolated_openai(request: BasicLLMRequest, messages: list) -> str:
        """使用独立 OpenAI 客户端调用"""
        client = LLMClientFactory._create_isolated_openai_client(request)

        # 转换消息格式
        openai_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                openai_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, dict):
                openai_messages.append(msg)
            else:
                # 尝试获取消息类型和内容
                role = getattr(msg, "type", "user")
                content = getattr(msg, "content", str(msg))
                openai_messages.append({"role": role, "content": content})

        # 准备调用参数
        call_kwargs = {
            "model": request.model,
            "messages": openai_messages,
            "temperature": _request_temperature(request),
        }
        if request.max_output_tokens > 0:
            call_kwargs["max_tokens"] = request.max_output_tokens

        response_format = (request.extra_config or {}).get("response_format")
        if response_format:
            call_kwargs["response_format"] = response_format

        # 隔离调用一律关闭 thinking，避免规划/结构化输出被 reasoning 污染
        thinking_body = _build_openai_thinking_extra_body(request.model, show_think=False)
        if thinking_body:
            call_kwargs["extra_body"] = thinking_body

        # 直接调用原生 OpenAI API；部分网关不支持 response_format，自动降级重试
        try:
            response = client.chat.completions.create(**call_kwargs)
        except Exception as exc:
            if not response_format or not _is_unsupported_response_format_error(exc):
                raise
            call_kwargs.pop("response_format", None)
            response = client.chat.completions.create(**call_kwargs)
        usage = getattr(response, "usage", None)
        finish_reason = str(getattr(response.choices[0], "finish_reason", "") or "")
        message = response.choices[0].message
        text = _normalize_message_content(getattr(message, "content", None))
        if not text:
            refusal = getattr(message, "refusal", None)
            if refusal:
                text = _normalize_message_content(refusal)
                finish_reason = finish_reason or "refusal"
        _attach_isolated_openai_result(
            request,
            thinking_body=thinking_body,
            finish_reason=finish_reason,
            usage=usage,
            message=message,
            text=text,
        )
        return text

    @staticmethod
    def _invoke_isolated_anthropic(request: BasicLLMRequest, messages: list) -> str:
        """使用独立 Anthropic 客户端调用"""
        client = LLMClientFactory._create_isolated_anthropic_client(request)

        # 转换消息格式 - Anthropic 格式与 OpenAI 类似但有细微差别
        anthropic_messages = []
        system_message = None

        for msg in messages:
            if isinstance(msg, HumanMessage):
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, dict):
                # Anthropic 的 system 消息需要单独处理
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                else:
                    anthropic_messages.append(msg)
            else:
                role = getattr(msg, "type", "user")
                content = getattr(msg, "content", str(msg))
                if role == "system":
                    system_message = content
                else:
                    mapped_role = "assistant" if role in {"assistant", "ai"} else "user"
                    anthropic_messages.append({"role": mapped_role, "content": content})

        # 准备调用参数
        call_kwargs = {
            "model": request.model,
            "messages": anthropic_messages,
            "temperature": _request_temperature(request),
            "max_tokens": request.max_output_tokens or 4096,  # Anthropic 要求必须指定 max_tokens
        }

        if system_message:
            call_kwargs["system"] = system_message

        # 直接调用原生 Anthropic API
        response = client.messages.create(**call_kwargs)
        usage = getattr(response, "usage", None)
        finish_reason = str(getattr(response, "stop_reason", "") or "")
        request.extra_config = {
            **(request.extra_config or {}),
            "_isolated_finish_reason": finish_reason,
            "_isolated_output_truncated": finish_reason.casefold() in {"length", "max_tokens", "max_output_tokens", "token_limit"},
        }
        if usage is not None:
            request.extra_config = {
                **(request.extra_config or {}),
                "_isolated_usage": {
                    "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                    "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                },
            }
        return _normalize_message_content(response.content)

    @staticmethod
    def stream_isolated(request: BasicLLMRequest, messages: list):
        """Yield text deltas from an isolated streaming LLM call.

        Finish / truncation flags are written onto ``request.extra_config`` when the
        stream completes (same keys as ``invoke_isolated``).
        """
        if request.protocol_type == "anthropic":
            yield from LLMClientFactory._stream_isolated_anthropic(request, messages)
        else:
            yield from LLMClientFactory._stream_isolated_openai(request, messages)

    @staticmethod
    def _normalize_openai_messages(messages: list) -> list:
        openai_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                openai_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, dict):
                openai_messages.append(msg)
            else:
                role = getattr(msg, "type", "user")
                content = getattr(msg, "content", str(msg))
                openai_messages.append({"role": role, "content": content})
        return openai_messages

    @staticmethod
    def _stream_isolated_openai(request: BasicLLMRequest, messages: list):
        client = LLMClientFactory._create_isolated_openai_client(request)
        openai_messages = LLMClientFactory._normalize_openai_messages(messages)
        call_kwargs = {
            "model": request.model,
            "messages": openai_messages,
            "temperature": _request_temperature(request),
            "stream": True,
        }
        if request.max_output_tokens > 0:
            call_kwargs["max_tokens"] = request.max_output_tokens

        response_format = (request.extra_config or {}).get("response_format")
        if response_format:
            call_kwargs["response_format"] = response_format

        thinking_body = _build_openai_thinking_extra_body(request.model, show_think=False)
        if thinking_body:
            call_kwargs["extra_body"] = thinking_body

        try:
            stream = client.chat.completions.create(**call_kwargs)
        except Exception as exc:
            if not response_format or not _is_unsupported_response_format_error(exc):
                raise
            call_kwargs.pop("response_format", None)
            stream = client.chat.completions.create(**call_kwargs)

        finish_reason = ""
        usage = None
        for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            reason = getattr(choice, "finish_reason", None)
            if reason:
                finish_reason = str(reason)
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            text = _normalize_message_content(content) if content else ""
            if text:
                yield text

        request.extra_config = {
            **(request.extra_config or {}),
            "_isolated_finish_reason": finish_reason,
            "_isolated_output_truncated": finish_reason.casefold() in {"length", "max_tokens", "max_output_tokens", "token_limit"},
        }
        if usage is not None:
            request.extra_config = {
                **(request.extra_config or {}),
                "_isolated_usage": {
                    "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                    "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                },
            }

    @staticmethod
    def _stream_isolated_anthropic(request: BasicLLMRequest, messages: list):
        client = LLMClientFactory._create_isolated_anthropic_client(request)
        anthropic_messages = []
        system_message = None
        for msg in messages:
            if isinstance(msg, HumanMessage):
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, dict):
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                else:
                    anthropic_messages.append(msg)
            else:
                role = getattr(msg, "type", "user")
                content = getattr(msg, "content", str(msg))
                if role == "system":
                    system_message = content
                else:
                    mapped_role = "assistant" if role in {"assistant", "ai"} else "user"
                    anthropic_messages.append({"role": mapped_role, "content": content})

        call_kwargs = {
            "model": request.model,
            "messages": anthropic_messages,
            "temperature": _request_temperature(request),
            "max_tokens": request.max_output_tokens or 4096,
        }
        if system_message:
            call_kwargs["system"] = system_message

        finish_reason = ""
        usage = None
        with client.messages.stream(**call_kwargs) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
            final = stream.get_final_message()
            finish_reason = str(getattr(final, "stop_reason", "") or "")
            usage = getattr(final, "usage", None)

        request.extra_config = {
            **(request.extra_config or {}),
            "_isolated_finish_reason": finish_reason,
            "_isolated_output_truncated": finish_reason.casefold() in {"length", "max_tokens", "max_output_tokens", "token_limit"},
        }
        if usage is not None:
            request.extra_config = {
                **(request.extra_config or {}),
                "_isolated_usage": {
                    "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                    "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
                },
            }
