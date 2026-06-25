"""LLM客户端工厂类,用于创建不同用途的LLM客户端"""

import os
from typing import Union

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.ssrf_validator import SSRFValidator
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.anthropic_capabilities import build_anthropic_runtime_capabilities
from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import AnthropicCompatibleChatClient


class LLMClientFactory:
    """LLM客户端工厂"""

    @staticmethod
    def create_client(request: BasicLLMRequest, disable_stream=False, isolated=False) -> BaseChatModel:
        """
        创建LLM客户端

        Args:
            request: LLM请求对象
            disable_stream: 是否禁用流式输出
            isolated: 是否创建独立客户端(不被LangGraph跟踪),用于内部调用如问题改写

        Returns:
            BaseChatModel客户端实例 (ChatOpenAI 或 ChatAnthropic)
        """
        capabilities = build_anthropic_runtime_capabilities(
            getattr(request, "vendor_type", ""),
            request.protocol_type,
        )
        if capabilities.use_anthropic_compatible_adapter:
            llm = LLMClientFactory._create_anthropic_compatible_client(request, disable_stream)
        elif request.protocol_type == "anthropic":
            llm = LLMClientFactory._create_anthropic_client(request, disable_stream)
        else:
            llm = LLMClientFactory._create_openai_client(request, disable_stream)

        # 如果需要隔离,则禁用callbacks以避免被LangGraph捕获
        if isolated:
            llm.callbacks = None

        return llm

    @staticmethod
    def _create_openai_client(request: BasicLLMRequest, disable_stream: bool) -> ChatOpenAI:
        """创建 OpenAI 兼容客户端"""
        # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
        base_url = request.openai_api_base
        if base_url:
            SSRFValidator.validate_llm_endpoint(base_url)

        llm = ChatOpenAI(
            model=request.model,
            base_url=base_url,
            api_key=request.openai_api_key,
            temperature=request.temperature,
            disable_streaming=disable_stream,
            timeout=int(os.getenv("LLM_INVOKE_TIMEOUT", "60")),
        )

        if llm.extra_body is None:
            llm.extra_body = {}

        show_think = bool((request.extra_config or {}).get("show_think", True))
        model_lower = request.model.lower()
        if "qwen" in model_lower:
            llm.extra_body["enable_thinking"] = show_think
        elif "deepseek" in model_lower:
            thinking_type = "enabled" if show_think else "disabled"
            llm.extra_body["thinking"] = {"type": thinking_type}
        elif "gemma" in model_lower:
            # Gemma-4 通过 vLLM chat_template_kwargs 控制 thinking 模式
            llm.extra_body["chat_template_kwargs"] = {"enable_thinking": show_think}

        return llm

    @staticmethod
    def _create_anthropic_client(request: BasicLLMRequest, disable_stream: bool) -> ChatAnthropic:
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
            temperature=request.temperature,
            disable_streaming=disable_stream,
            timeout=int(os.getenv("LLM_INVOKE_TIMEOUT", "60")),
            model_kwargs=model_kwargs if model_kwargs else None,
        )

        logger.info(f"[LLMClientFactory] ChatAnthropic client: model={request.model}, base_url={base_url}, api_key={request.openai_api_key}")

        return llm

    @staticmethod
    def _create_anthropic_compatible_client(request: BasicLLMRequest, disable_stream: bool) -> AnthropicCompatibleChatClient:
        """Create a thin runtime client for Anthropic-compatible vendors."""
        base_url = request.openai_api_base
        if not base_url or base_url == "https://api.openai.com":
            base_url = "https://api.anthropic.com"

        SSRFValidator.validate_llm_endpoint(base_url)

        logger.info(
            f"[LLMClientFactory] AnthropicCompatible client: model={request.model}, "
            f"base_url={base_url}, vendor_type={getattr(request, 'vendor_type', '')}, "
            f"api_key={request.openai_api_key}"
        )

        return AnthropicCompatibleChatClient(
            model=request.model,
            api_key=request.openai_api_key,
            api_base=base_url,
            temperature=request.temperature,
            disable_streaming=disable_stream,
            timeout=15,
            vendor_type=getattr(request, "vendor_type", ""),
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
        kwargs = {"api_key": request.openai_api_key, "timeout": 60.0}
        if request.openai_api_base:
            # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
            SSRFValidator.validate_llm_endpoint(request.openai_api_base)
            kwargs["base_url"] = request.openai_api_base
        return OpenAI(**kwargs)

    @staticmethod
    def _create_isolated_anthropic_client(request: BasicLLMRequest) -> anthropic.Anthropic:
        """创建独立的原生 Anthropic 客户端"""
        base_url = request.openai_api_base
        if not base_url or base_url == "https://api.openai.com":
            base_url = "https://api.anthropic.com"

        # SSRF 防护：验证 API base URL（宽松模式，允许内网 LLM 服务）
        SSRFValidator.validate_llm_endpoint(base_url)

        return anthropic.Anthropic(
            api_key=request.openai_api_key,
            base_url=base_url,
            timeout=60.0,
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
            "temperature": request.temperature,
        }

        # 添加 Qwen/DeepSeek/Gemma 模型的特殊配置（隔离调用禁用 thinking）
        model_lower = request.model.lower()
        if "qwen" in model_lower:
            call_kwargs["extra_body"] = {"enable_thinking": False}
        elif "deepseek" in model_lower:
            call_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif "gemma" in model_lower:
            call_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        # 直接调用原生 OpenAI API
        response = client.chat.completions.create(**call_kwargs)
        return response.choices[0].message.content

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
                    anthropic_messages.append({"role": role, "content": content})

        # 准备调用参数
        call_kwargs = {
            "model": request.model,
            "messages": anthropic_messages,
            "temperature": request.temperature,
            "max_tokens": 4096,  # Anthropic 要求必须指定 max_tokens
        }

        if system_message:
            call_kwargs["system"] = system_message

        # 直接调用原生 Anthropic API
        response = client.messages.create(**call_kwargs)
        return response.content[0].text
