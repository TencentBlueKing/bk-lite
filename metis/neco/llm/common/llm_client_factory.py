"""LLM客户端工厂类,用于创建不同用途的LLM客户端"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from openai import OpenAI
from neco.llm.chain.entity import BasicLLMRequest


class LLMClientFactory:
    """LLM客户端工厂"""

    @staticmethod
    def create_client(request: BasicLLMRequest, disable_stream=False, isolated=False) -> ChatOpenAI:
        """
        创建LLM客户端

        Args:
            request: LLM请求对象
            disable_stream: 是否禁用流式输出
            isolated: 是否创建独立客户端(不被LangGraph跟踪),用于内部调用如问题改写

        Returns:
            ChatOpenAI客户端实例
        """
        llm = ChatOpenAI(
            model=request.model,
            base_url=request.openai_api_base,
            api_key=request.openai_api_key,
            temperature=request.temperature,
            disable_streaming=disable_stream,
            timeout=3000
        )

        if llm.extra_body is None:
            llm.extra_body = {}

        if disable_stream and 'qwen' in request.model.lower():
            llm.extra_body["enable_thinking"] = False

        # 如果需要隔离,则禁用callbacks以避免被LangGraph捕获
        if isolated:
            llm.callbacks = None

        return llm

    @staticmethod
    def create_isolated_client(request: BasicLLMRequest) -> OpenAI:
        """
        创建独立的原生OpenAI客户端,完全绕过LangChain/LangGraph追踪
        适用于内部调用场景,如问题改写、知识路由等

        Args:
            request: LLM请求对象

        Returns:
            原生OpenAI客户端实例
        """
        kwargs = {
            'api_key': request.openai_api_key,
            'timeout': 60.0
        }
        if request.openai_api_base:
            kwargs['base_url'] = request.openai_api_base

        return OpenAI(**kwargs)

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
        client = LLMClientFactory.create_isolated_client(request)

        # 转换消息格式
        openai_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                openai_messages.append(
                    {"role": "user", "content": msg.content})
            elif isinstance(msg, dict):
                openai_messages.append(msg)
            else:
                # 尝试获取消息类型和内容
                role = getattr(msg, 'type', 'user')
                content = getattr(msg, 'content', str(msg))
                openai_messages.append({"role": role, "content": content})

        # 准备调用参数
        call_kwargs = {
            'model': request.model,
            'messages': openai_messages,
            'temperature': request.temperature,
        }

        # 添加 Qwen 模型的特殊配置
        if 'qwen' in request.model.lower():
            call_kwargs['extra_body'] = {"enable_thinking": False}

        # 直接调用原生 OpenAI API
        response = client.chat.completions.create(**call_kwargs)
        return response.choices[0].message.content
