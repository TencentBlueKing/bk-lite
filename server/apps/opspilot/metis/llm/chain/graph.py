import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import tiktoken
from ag_ui.core import (
    CustomEvent,
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, BasicLLMResponse


async def _merge_async_streams(
    langgraph_stream,
    event_queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> AsyncGenerator[Any, None]:
    """
    合并 LangGraph 消息流和浏览器事件队列，实现真正的实时流式输出

    使用 asyncio.create_task 并发消费两个源:
    1. LangGraph stream - 产生 AI 消息块
    2. event_queue - 产生浏览器步骤事件

    Args:
        langgraph_stream: LangGraph 的 astream 返回的异步迭代器
        event_queue: 浏览器步骤事件队列
        stop_event: 停止信号，用于通知队列消费者停止

    Yields:
        合并后的事件，类型为 tuple:
        - ("langgraph", chunk) - 来自 LangGraph 的消息块
        - ("browser", event) - 来自浏览器的 SSE 事件字符串
    """
    output_queue: asyncio.Queue = asyncio.Queue()

    async def langgraph_consumer():
        """消费 LangGraph 流并推送到输出队列"""
        try:
            async for chunk in langgraph_stream:
                await output_queue.put(("langgraph", chunk))
        finally:
            # 标记 LangGraph 流结束
            await output_queue.put(("langgraph_done", None))

    async def browser_event_consumer():
        """消费浏览器事件队列并推送到输出队列"""
        while not stop_event.is_set():
            try:
                # 使用短超时，以便能响应 stop_event
                event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                await output_queue.put(("browser", event))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Browser event consumer error: {e}")
                break

    # 启动两个并发消费者
    langgraph_task = asyncio.create_task(langgraph_consumer())
    browser_task = asyncio.create_task(browser_event_consumer())

    langgraph_done = False

    try:
        while True:
            try:
                # 从合并队列获取事件
                event_type, data = await asyncio.wait_for(output_queue.get(), timeout=0.1)

                if event_type == "langgraph_done":
                    langgraph_done = True
                    # 设置停止信号，通知浏览器消费者停止
                    stop_event.set()
                    # 继续处理剩余的浏览器事件
                    continue
                elif event_type == "langgraph":
                    yield ("langgraph", data)
                elif event_type == "browser":
                    yield ("browser", data)

            except asyncio.TimeoutError:
                # 如果 LangGraph 已完成且输出队列为空，则退出
                if langgraph_done and output_queue.empty():
                    break
                continue

    finally:
        # 清理: 设置停止信号并取消任务
        stop_event.set()
        browser_task.cancel()

        # 等待任务完成
        try:
            await langgraph_task
        except Exception:
            pass

        try:
            await browser_task
        except asyncio.CancelledError:
            pass


def create_browser_step_callback(
    event_queue: asyncio.Queue,
    encoder: EventEncoder,
) -> Callable[[Dict[str, Any]], None]:
    """
    创建浏览器步骤回调函数，用于将 browser-use 的执行进度推送到 SSE 事件队列

    Args:
        event_queue: 异步事件队列，用于存放待发送的 SSE 事件
        encoder: ag_ui 事件编码器

    Returns:
        回调函数，接收 BrowserStepInfo 字典并将其转换为 CustomEvent 推送到队列
    """

    def step_callback(step_info: Dict[str, Any]) -> None:
        """
        浏览器步骤回调 - 将步骤信息转换为 CustomEvent 并推送到队列

        Args:
            step_info: BrowserStepInfo 字典，包含:
                - step_number: 当前步骤编号
                - max_steps: 最大步骤数
                - url: 当前页面 URL
                - title: 页面标题
                - thinking: AI 思考内容
                - evaluation: 执行评估
                - memory: 记忆内容
                - next_goal: 下一步目标
                - actions: 执行的动作列表
                - screenshot: base64 编码的截图（可选）
        """
        try:
            # 构建 CustomEvent
            logger.debug(f"Browser step callback triggered: step {step_info.get('step_number')}, goal: {step_info.get('next_goal')}")
            event = CustomEvent(
                type=EventType.CUSTOM,
                name="browser_step_progress",
                value={
                    "step_number": step_info.get("step_number", 0),
                    "max_steps": step_info.get("max_steps", 0),
                    "url": step_info.get("url", ""),
                    "title": step_info.get("title", ""),
                    "thinking": step_info.get("thinking"),
                    "evaluation": step_info.get("evaluation"),
                    "memory": step_info.get("memory"),
                    "next_goal": step_info.get("next_goal"),
                    "actions": step_info.get("actions", []),
                    # 不包含 screenshot 以减少传输大小，前端如需截图可单独请求
                    "has_screenshot": bool(step_info.get("screenshot")),
                },
            )

            # 编码并推送到队列（非阻塞）
            encoded_event = encoder.encode(event)
            try:
                event_queue.put_nowait(encoded_event)
            except asyncio.QueueFull:
                logger.warning("Browser step event queue is full, dropping event")

        except Exception as e:
            logger.error(f"Error in browser step callback: {e}")

    return step_callback


class BasicGraph(ABC):
    """基础图执行类，提供流式和非流式执行能力"""

    async def filter_messages(self, chunk: BaseMessage) -> str:
        """过滤消息，只返回 AI 消息内容"""
        if isinstance(chunk[0], (SystemMessage, HumanMessage)):
            return ""
        return chunk[0].content

    def count_tokens(self, text: str, encoding_name: str = "gpt-4o") -> int:
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
                print(chunk[0].content, end="", flush=True)
        print("\n")

    def print_chunk(self, result):
        """同步打印流式输出的内容块"""
        for chunk in result:
            if isinstance(chunk[0], AIMessageChunk):
                print(chunk[0].content, end="", flush=True)
        print("\n")

    def prepare_graph(self, graph_builder, node_builder) -> str:
        """准备基础图结构，添加节点和边"""
        graph_builder.add_node("prompt_message_node", node_builder.prompt_message_node)
        graph_builder.add_node("add_chat_history_node", node_builder.add_chat_history_node)
        graph_builder.add_node("naive_rag_node", node_builder.naive_rag_node)
        graph_builder.add_node("user_message_node", node_builder.user_message_node)
        graph_builder.add_node("suggest_question_node", node_builder.suggest_question_node)

        graph_builder.add_edge(START, "prompt_message_node")
        graph_builder.add_edge("prompt_message_node", "suggest_question_node")
        graph_builder.add_edge("suggest_question_node", "add_chat_history_node")
        graph_builder.add_edge("add_chat_history_node", "user_message_node")
        graph_builder.add_edge("user_message_node", "naive_rag_node")

        return "naive_rag_node"

    async def invoke(
        self,
        graph,
        request: BasicLLMRequest,
        stream_mode: str = "values",
        extra_configurable: Optional[Dict[str, Any]] = None,
    ):
        """执行图，支持流式和非流式模式

        Args:
            graph: 编译后的图
            request: LLM 请求对象
            stream_mode: 流模式，'values' 或 'messages'
            extra_configurable: 额外的 configurable 配置，如 browser_step_callback

        Returns:
            执行结果或流
        """
        config = {
            "recursion_limit": 50,
            "trace_id": str(uuid.uuid4()),
            "configurable": {
                "graph_request": request,
                "user_id": request.user_id or "",
                **request.extra_config,
                **(extra_configurable or {}),
            },
        }

        if stream_mode == "values":
            return await graph.ainvoke(request, config)

        if stream_mode == "messages":
            return graph.astream(request, config, stream_mode=stream_mode)

    @abstractmethod
    async def compile_graph(self, request: BasicLLMRequest):
        """编译图结构，由子类实现"""
        pass

    async def stream(self, request: BasicLLMRequest):
        """流式执行，返回消息流"""
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request, stream_mode="messages")
        return result

    async def agui_stream(self, request: BasicLLMRequest) -> AsyncGenerator[str, None]:
        """
        使用 agui 协议以 SSE 格式流式输出事件

        支持浏览器工具执行进度的实时流式推送。当使用 browser-use 工具时，
        每个执行步骤都会通过 CustomEvent (name="browser_step_progress") 实时推送。

        使用 _merge_async_streams 并发消费 LangGraph 流和浏览器事件队列，
        实现真正的实时流式输出，而不是等待 LangGraph 产生 chunk 时才检查队列。

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

        # 创建浏览器步骤事件队列和回调
        browser_event_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        browser_step_callback = create_browser_step_callback(browser_event_queue, encoder)

        # 停止信号，用于通知队列消费者停止
        stop_event = asyncio.Event()

        try:
            # 发送 RUN_STARTED 事件
            yield encoder.encode(
                RunStartedEvent(
                    type=EventType.RUN_STARTED,
                    thread_id=thread_id,
                    run_id=run_id,
                    timestamp=int(time.time() * 1000),
                )
            )

            # 获取消息流，注入浏览器步骤回调
            graph = await self.compile_graph(request)
            result = await self.invoke(
                graph,
                request,
                stream_mode="messages",
                extra_configurable={"browser_step_callback": browser_step_callback},
            )

            # 使用并发流合并器处理 LangGraph 流和浏览器事件
            try:
                async for event_type, data in _merge_async_streams(result, browser_event_queue, stop_event):
                    # 处理浏览器步骤事件 - 已编码，直接 yield
                    if event_type == "browser":
                        yield data
                        continue

                    # 处理 LangGraph 消息块
                    chunk = data
                    if not chunk:
                        continue

                    message = chunk[0] if isinstance(chunk, (list, tuple)) else chunk

                    # 处理 AI 消息块
                    if isinstance(message, AIMessageChunk):
                        async for event in self._handle_ai_message_chunk(
                            message,
                            encoder,
                            run_id,
                            current_message_id,
                            current_tool_calls,
                        ):
                            yield event
                        # 更新 current_message_id（如果是首次创建）
                        if message.content and current_message_id is None:
                            current_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"

                    # 处理工具执行结果
                    elif isinstance(message, ToolMessage):
                        yield encoder.encode(
                            ToolCallResultEvent(
                                type=EventType.TOOL_CALL_RESULT,
                                message_id=f"result_{uuid.uuid4()}",
                                tool_call_id=getattr(message, "tool_call_id", str(uuid.uuid4())),
                                content=str(message.content),
                                role="tool",
                                timestamp=int(time.time() * 1000),
                            )
                        )

                    # 处理完整 AI 消息（非流式块）
                    elif isinstance(message, AIMessage) and not isinstance(message, AIMessageChunk):
                        # 为每个完整 AIMessage 创建独立的消息 ID
                        complete_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"

                        # 处理工具调用（如果存在）
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for event in self._handle_tool_calls_sync(
                                message.tool_calls,
                                encoder,
                                complete_message_id,
                                current_tool_calls,
                            ):
                                yield event

                        # 处理文本内容（如果存在）
                        if message.content:
                            yield encoder.encode(
                                TextMessageStartEvent(
                                    type=EventType.TEXT_MESSAGE_START,
                                    message_id=complete_message_id,
                                    role="assistant",
                                    timestamp=int(time.time() * 1000),
                                )
                            )

                            yield encoder.encode(
                                TextMessageContentEvent(
                                    type=EventType.TEXT_MESSAGE_CONTENT,
                                    message_id=complete_message_id,
                                    delta=message.content,
                                    timestamp=int(time.time() * 1000),
                                )
                            )

                            yield encoder.encode(
                                TextMessageEndEvent(
                                    type=EventType.TEXT_MESSAGE_END,
                                    message_id=complete_message_id,
                                    timestamp=int(time.time() * 1000),
                                )
                            )

            except Exception:
                # 继续抛出异常，让外层 catch 处理
                raise

            # 发送消息结束事件
            if current_message_id is not None:
                yield encoder.encode(
                    TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=current_message_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

            # 发送 RUN_FINISHED 事件
            yield encoder.encode(
                RunFinishedEvent(
                    type=EventType.RUN_FINISHED,
                    thread_id=thread_id,
                    run_id=run_id,
                    timestamp=int(time.time() * 1000),
                )
            )

        except Exception as e:
            logger.exception(f"agui_stream 执行出错: {e}")
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=str(e),
                    code="EXECUTION_ERROR",
                    timestamp=int(time.time() * 1000),
                )
            )
        finally:
            # 确保停止信号被设置，清理后台任务
            stop_event.set()

    async def _handle_ai_message_chunk(
        self,
        message: AIMessageChunk,
        encoder: EventEncoder,
        run_id: str,
        current_message_id: str,
        current_tool_calls: Dict[str, Dict],
    ):
        """处理 AI 消息块，包括文本内容和工具调用"""
        content = message.content

        # 处理文本内容
        if content:
            # 首次输出内容时发送 TEXT_MESSAGE_START
            if current_message_id is None:
                current_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"
                yield encoder.encode(
                    TextMessageStartEvent(
                        type=EventType.TEXT_MESSAGE_START,
                        message_id=current_message_id,
                        role="assistant",
                        timestamp=int(time.time() * 1000),
                    )
                )

            # 发送内容块
            yield encoder.encode(
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=current_message_id,
                    delta=content,
                    timestamp=int(time.time() * 1000),
                )
            )

        # 处理工具调用
        if hasattr(message, "tool_calls") and message.tool_calls:
            async for event in self._handle_tool_calls(message.tool_calls, encoder, current_message_id, current_tool_calls):
                yield event

    async def _handle_tool_calls(
        self,
        tool_calls: List[Dict],
        encoder: EventEncoder,
        parent_message_id: str,
        current_tool_calls: Dict[str, Dict],
    ) -> AsyncGenerator[str, None]:
        """处理工具调用事件（异步生成器版本，用于流式场景）"""
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id", f"tool_{uuid.uuid4()}")
            tool_name = tool_call.get("name", "unknown")

            # 如果是新的工具调用
            if tool_call_id not in current_tool_calls:
                current_tool_calls[tool_call_id] = {"name": tool_name, "started": True}

                # 发送 TOOL_CALL_START
                yield encoder.encode(
                    ToolCallStartEvent(
                        type=EventType.TOOL_CALL_START,
                        tool_call_id=tool_call_id,
                        tool_call_name=tool_name,
                        parent_message_id=parent_message_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

                # 发送工具参数
                if "args" in tool_call:
                    yield encoder.encode(
                        ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=tool_call_id,
                            delta=json.dumps(tool_call["args"], ensure_ascii=False),
                            timestamp=int(time.time() * 1000),
                        )
                    )

                # 发送 TOOL_CALL_END
                yield encoder.encode(
                    ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=tool_call_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

    def _handle_tool_calls_sync(
        self,
        tool_calls: List[Dict],
        encoder: EventEncoder,
        parent_message_id: str,
        current_tool_calls: Dict[str, Dict],
    ):
        """处理工具调用事件（同步生成器版本，用于完整消息）"""
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id", f"tool_{uuid.uuid4()}")
            tool_name = tool_call.get("name", "unknown")

            # 如果是新的工具调用
            if tool_call_id not in current_tool_calls:
                current_tool_calls[tool_call_id] = {"name": tool_name, "started": True}

                # 发送 TOOL_CALL_START
                yield encoder.encode(
                    ToolCallStartEvent(
                        type=EventType.TOOL_CALL_START,
                        tool_call_id=tool_call_id,
                        tool_call_name=tool_name,
                        parent_message_id=parent_message_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

                # 发送工具参数
                if "args" in tool_call:
                    yield encoder.encode(
                        ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=tool_call_id,
                            delta=json.dumps(tool_call["args"], ensure_ascii=False),
                            timestamp=int(time.time() * 1000),
                        )
                    )

                # 发送 TOOL_CALL_END
                yield encoder.encode(
                    ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=tool_call_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

    async def execute(self, request: BasicLLMRequest) -> BasicLLMResponse:
        """执行图并返回完整响应，包含 token 统计"""
        try:
            graph = await self.compile_graph(request)
            result = await self.invoke(graph, request)

            prompt_token = 0
            completion_token = 0

            for message in result["messages"]:
                if isinstance(message, AIMessage) and "token_usage" in message.response_metadata:
                    token_usage = message.response_metadata["token_usage"]
                    prompt_token += token_usage["prompt_tokens"]
                    completion_token += token_usage["completion_tokens"]

            last_message_content = result["messages"][-1].content if result["messages"] else ""
            return BasicLLMResponse(
                message=last_message_content,
                total_tokens=prompt_token + completion_token,
                prompt_tokens=prompt_token,
                completion_tokens=completion_token,
            )
        except BaseException as e:
            # 处理所有异常，包括 TaskGroup 异常
            error_msg = str(e)

            # 提取 TaskGroup 中的实际错误信息
            if "unhandled errors in a TaskGroup" in error_msg:
                if hasattr(e, "__cause__") and e.__cause__:
                    error_msg = f"TaskGroup error: {str(e.__cause__)}"
                elif hasattr(e, "exceptions"):
                    # ExceptionGroup 有 exceptions 属性
                    sub_errors = [str(ex) for ex in e.exceptions]
                    error_msg = f"TaskGroup errors: {', '.join(sub_errors)}"

            logger.error(f"Graph execute 执行失败: {error_msg}", exc_info=True)

            # 重新抛出异常，让上层处理
            raise RuntimeError(f"Agent execution failed: {error_msg}") from e
