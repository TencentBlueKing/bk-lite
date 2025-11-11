import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List

import tiktoken
from ag_ui.core import (
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.base import BaseMessage
from langgraph.constants import START
from loguru import logger

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse


class BasicGraph(ABC):
    """基础图执行类，提供流式和非流式执行能力"""

    async def filter_messages(self, chunk: BaseMessage) -> str:
        """过滤消息，只返回 AI 消息内容"""
        if isinstance(chunk[0], (SystemMessage, HumanMessage)):
            return ""
        return chunk[0].content

    def count_tokens(self, text: str, encoding_name: str = 'gpt-4o') -> int:
        """计算文本的 Token 数量"""
        try:
            encoding = tiktoken.encoding_for_model(encoding_name)
            tokens = encoding.encode(text)
            return len(tokens)
        except KeyError:
            logger.warning(f"模型 {encoding_name} 不支持。默认回退到通用编码器。")
            encoding = tiktoken.get_encoding("cl100k_base")
            tokens = encoding.encode(text)
            return len(tokens)

    async def aprint_chunk(self, result):
        """异步打印流式输出的内容块"""
        async for chunk in result:
            if isinstance(chunk[0], AIMessageChunk):
                print(chunk[0].content, end='', flush=True)
        print('\n')

    def print_chunk(self, result):
        """同步打印流式输出的内容块"""
        for chunk in result:
            if isinstance(chunk[0], AIMessageChunk):
                print(chunk[0].content, end='', flush=True)
        print('\n')

    def prepare_graph(self, graph_builder, node_builder) -> str:
        """准备基础图结构，添加节点和边"""
        graph_builder.add_node("prompt_message_node",
                               node_builder.prompt_message_node)
        graph_builder.add_node("add_chat_history_node",
                               node_builder.add_chat_history_node)
        graph_builder.add_node("naive_rag_node", node_builder.naive_rag_node)
        graph_builder.add_node("user_message_node",
                               node_builder.user_message_node)
        graph_builder.add_node("suggest_question_node",
                               node_builder.suggest_question_node)

        graph_builder.add_edge(START, "prompt_message_node")
        graph_builder.add_edge("prompt_message_node", "suggest_question_node")
        graph_builder.add_edge("suggest_question_node",
                               "add_chat_history_node")
        graph_builder.add_edge("add_chat_history_node", "user_message_node")
        graph_builder.add_edge("user_message_node", "naive_rag_node")

        return 'naive_rag_node'

    async def invoke(self, graph, request: BasicLLMRequest, stream_mode: str = 'values'):
        """执行图，支持流式和非流式模式"""
        config = {
            "graph_request": request,
            "recursion_limit": 50,
            "trace_id": str(uuid.uuid4()),
            "configurable": {
                **request.extra_config,
            }
        }

        if stream_mode == 'values':
            return await graph.ainvoke(request, config)

        if stream_mode == 'messages':
            return graph.astream(request, config, stream_mode=stream_mode)

    @abstractmethod
    async def compile_graph(self, request: BasicLLMRequest):
        """编译图结构，由子类实现"""
        pass

    async def stream(self, request: BasicLLMRequest):
        """流式执行，返回消息流"""
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request, stream_mode='messages')
        return result

    async def agui_stream(self, request: BasicLLMRequest) -> AsyncGenerator[str, None]:
        """
        使用 agui 协议以 SSE 格式流式输出事件

        Args:
            request: 基础 LLM 请求对象

        Yields:
            SSE 格式的事件字符串: "data: {json}\\n\\n"
        """
        encoder = EventEncoder()
        run_id = str(uuid.uuid4())
        thread_id = request.thread_id or str(uuid.uuid4())
        current_message_id = None
        current_tool_calls: Dict[str, Dict] = {}

        try:
            # 发送 RUN_STARTED 事件
            yield encoder.encode(RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=thread_id,
                run_id=run_id,
                timestamp=int(time.time() * 1000)
            ))

            # 获取消息流
            graph = await self.compile_graph(request)
            result = await self.invoke(graph, request, stream_mode='messages')

            # 处理流式消息
            async for chunk in result:
                if not chunk:
                    continue

                message = chunk[0] if isinstance(
                    chunk, (list, tuple)) else chunk

                # 处理 AI 消息块
                if isinstance(message, AIMessageChunk):
                    await self._handle_ai_message_chunk(
                        message, encoder, run_id, current_message_id, current_tool_calls
                    )
                    # 更新 current_message_id（如果是首次创建）
                    if message.content and current_message_id is None:
                        current_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"

                # 处理工具执行结果
                elif isinstance(message, ToolMessage):
                    yield encoder.encode(ToolCallResultEvent(
                        type=EventType.TOOL_CALL_RESULT,
                        message_id=f"result_{uuid.uuid4()}",
                        tool_call_id=getattr(
                            message, 'tool_call_id', str(uuid.uuid4())),
                        content=str(message.content),
                        role="tool",
                        timestamp=int(time.time() * 1000)
                    ))

                # 处理完整 AI 消息（非流式块）
                elif isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk):
                    # 为每个完整 AIMessage 创建独立的消息 ID
                    complete_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"

                    # 处理工具调用（如果存在）
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        for event in self._handle_tool_calls_sync(
                            message.tool_calls, encoder, complete_message_id, current_tool_calls
                        ):
                            yield event

                    # 处理文本内容（如果存在）
                    if message.content:
                        yield encoder.encode(TextMessageStartEvent(
                            type=EventType.TEXT_MESSAGE_START,
                            message_id=complete_message_id,
                            role="assistant",
                            timestamp=int(time.time() * 1000)
                        ))

                        yield encoder.encode(TextMessageContentEvent(
                            type=EventType.TEXT_MESSAGE_CONTENT,
                            message_id=complete_message_id,
                            delta=message.content,
                            timestamp=int(time.time() * 1000)
                        ))

                        yield encoder.encode(TextMessageEndEvent(
                            type=EventType.TEXT_MESSAGE_END,
                            message_id=complete_message_id,
                            timestamp=int(time.time() * 1000)
                        ))

            # 发送消息结束事件
            if current_message_id is not None:
                yield encoder.encode(TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=current_message_id,
                    timestamp=int(time.time() * 1000)
                ))

            # 发送 RUN_FINISHED 事件
            yield encoder.encode(RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id,
                timestamp=int(time.time() * 1000)
            ))

        except Exception as e:
            logger.error(f"agui_stream 执行出错: {e}", exc_info=True)
            yield encoder.encode(RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=str(e),
                code="EXECUTION_ERROR",
                timestamp=int(time.time() * 1000)
            ))

    async def _handle_ai_message_chunk(
        self,
        message: AIMessageChunk,
        encoder: EventEncoder,
        run_id: str,
        current_message_id: str,
        current_tool_calls: Dict[str, Dict]
    ):
        """处理 AI 消息块，包括文本内容和工具调用"""
        content = message.content

        # 处理文本内容
        if content:
            # 首次输出内容时发送 TEXT_MESSAGE_START
            if current_message_id is None:
                current_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"
                yield encoder.encode(TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    message_id=current_message_id,
                    role="assistant",
                    timestamp=int(time.time() * 1000)
                ))

            # 发送内容块
            yield encoder.encode(TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=current_message_id,
                delta=content,
                timestamp=int(time.time() * 1000)
            ))

        # 处理工具调用
        if hasattr(message, 'tool_calls') and message.tool_calls:
            async for event in self._handle_tool_calls(
                message.tool_calls, encoder, current_message_id, current_tool_calls
            ):
                yield event

    async def _handle_tool_calls(
        self,
        tool_calls: List[Dict],
        encoder: EventEncoder,
        parent_message_id: str,
        current_tool_calls: Dict[str, Dict]
    ) -> AsyncGenerator[str, None]:
        """处理工具调用事件（异步生成器版本，用于流式场景）"""
        for tool_call in tool_calls:
            tool_call_id = tool_call.get('id') or tool_call.get(
                'tool_call_id', f"tool_{uuid.uuid4()}")
            tool_name = tool_call.get('name', 'unknown')

            # 如果是新的工具调用
            if tool_call_id not in current_tool_calls:
                current_tool_calls[tool_call_id] = {
                    'name': tool_name, 'started': True}

                # 发送 TOOL_CALL_START
                yield encoder.encode(ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=tool_call_id,
                    tool_call_name=tool_name,
                    parent_message_id=parent_message_id,
                    timestamp=int(time.time() * 1000)
                ))

                # 发送工具参数
                if 'args' in tool_call:
                    yield encoder.encode(ToolCallArgsEvent(
                        type=EventType.TOOL_CALL_ARGS,
                        tool_call_id=tool_call_id,
                        delta=json.dumps(
                            tool_call['args'], ensure_ascii=False),
                        timestamp=int(time.time() * 1000)
                    ))

                # 发送 TOOL_CALL_END
                yield encoder.encode(ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=tool_call_id,
                    timestamp=int(time.time() * 1000)
                ))

    def _handle_tool_calls_sync(
        self,
        tool_calls: List[Dict],
        encoder: EventEncoder,
        parent_message_id: str,
        current_tool_calls: Dict[str, Dict]
    ):
        """处理工具调用事件（同步生成器版本，用于完整消息）"""
        for tool_call in tool_calls:
            tool_call_id = tool_call.get('id') or tool_call.get(
                'tool_call_id', f"tool_{uuid.uuid4()}")
            tool_name = tool_call.get('name', 'unknown')

            # 如果是新的工具调用
            if tool_call_id not in current_tool_calls:
                current_tool_calls[tool_call_id] = {
                    'name': tool_name, 'started': True}

                # 发送 TOOL_CALL_START
                yield encoder.encode(ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=tool_call_id,
                    tool_call_name=tool_name,
                    parent_message_id=parent_message_id,
                    timestamp=int(time.time() * 1000)
                ))

                # 发送工具参数
                if 'args' in tool_call:
                    yield encoder.encode(ToolCallArgsEvent(
                        type=EventType.TOOL_CALL_ARGS,
                        tool_call_id=tool_call_id,
                        delta=json.dumps(
                            tool_call['args'], ensure_ascii=False),
                        timestamp=int(time.time() * 1000)
                    ))

                # 发送 TOOL_CALL_END
                yield encoder.encode(ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=tool_call_id,
                    timestamp=int(time.time() * 1000)
                ))

    async def execute(self, request: BasicLLMRequest) -> BasicLLMResponse:
        """执行图并返回完整响应，包含 token 统计"""
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request)

        prompt_token = 0
        completion_token = 0

        for message in result["messages"]:
            if isinstance(message, AIMessage) and 'token_usage' in message.response_metadata:
                token_usage = message.response_metadata['token_usage']
                prompt_token += token_usage['prompt_tokens']
                completion_token += token_usage['completion_tokens']

        last_message_content = result["messages"][-1].content if result["messages"] else ""

        return BasicLLMResponse(
            message=last_message_content,
            total_tokens=prompt_token + completion_token,
            prompt_tokens=prompt_token,
            completion_tokens=completion_token
        )
