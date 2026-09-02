import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from ag_ui.core import (
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ThinkingTextMessageContentEvent,
    ThinkingTextMessageEndEvent,
    ThinkingTextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.constants import START

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, BasicLLMResponse
from apps.opspilot.metis.llm.chain.report_renderers import find_unclosed_phantom_tool_call_start, strip_phantom_tool_calls
from apps.opspilot.metis.llm.common.llm_error_diagnostics import (
    classify_llm_error,
    format_llm_empty_response_log,
    format_llm_failure_log,
    summarize_llm_endpoint,
)
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

# deepagents 引擎内置工具（规划/虚拟文件系统/子代理）。这些是 agent 的内部
# 机制，默认不在 AG-UI/A2UI 流中展示，避免污染前端的工具调用视图。
# 可通过环境变量 OPSPILOT_AGUI_SHOW_BUILTIN_TOOLS=1
# 打开（用于调试 deepagent 的规划/文件读写过程）。
_DEEPAGENT_BUILTIN_TOOL_NAMES = frozenset(
    {
        "write_todos",
        "write_file",
        "read_file",
        "ls",
        "edit_file",
        "glob_search",
        "grep_search",
        "task",
    }
)

# 纯文本轮开播条件（仅 show_think=True 时启用；与模型无关，不按厂商硬编码）：
# 1) 连续多个正文 stream chunk 且未见 tool_call，或
# 2) 缓冲正文已明显长于典型「先旁白再调工具」短句（兼容 Minimax 等单大片输出）。
# 短旁白（通常 < 该阈值）继续缓冲，等 tool_call 到达后丢弃。
# show_think=False 时禁止开播：DeepSeek V4 等会在 tool_call 前输出大段分析旁白，
# 超过字符阈值就会泄漏到正文；改为整轮缓冲，有工具则丢弃，无工具再于 end 发出。
_AGUI_PLAIN_TEXT_LIVE_AFTER_CHUNKS = 2
_AGUI_PLAIN_TEXT_LIVE_AFTER_CHARS = 96
# 单次推送过长时拆成多条 TEXT_MESSAGE_CONTENT，避免「一整段一个 delta」。
_AGUI_LIVE_DELTA_CHARS = 64
# 低于 Next/undici body 空闲超时（约 300s），避免 RUN_STARTED 后长时间无 chunk 被掐流。
SSE_KEEPALIVE_INTERVAL_SECONDS = 15.0
STREAM_KEEPALIVE_EVENT_NAME = "stream_keepalive"


def _split_text_deltas(text: str, max_chars: int = _AGUI_LIVE_DELTA_CHARS) -> list[str]:
    """把长文本拆成多段 delta；不按模型名分支。"""
    value = str(text or "")
    if not value:
        return []
    if max_chars <= 0 or len(value) <= max_chars:
        return [value]
    return [value[i : i + max_chars] for i in range(0, len(value), max_chars)]


def encode_stream_keepalive(encoder: EventEncoder, phase: str) -> str:
    """SSE 保活：刷新代理读超时，并让前端知道流仍在跑。不进聊天气泡。"""
    return encoder.encode(
        CustomEvent(
            type=EventType.CUSTOM,
            name=STREAM_KEEPALIVE_EVENT_NAME,
            value={"phase": phase},
            timestamp=int(time.time() * 1000),
        )
    )


def iter_stream_keepalive_frames(encoder: EventEncoder, phase: str):
    """注释帧刷新中间代理；CUSTOM 帧给前端/DevTools。"""
    yield ": keepalive\n\n"
    yield encode_stream_keepalive(encoder, phase)


async def iter_sse_keepalive_until(task: asyncio.Task, encoder: EventEncoder, phase: str):
    """任务未完成时按间隔 yield SSE 保活。"""
    while not task.done():
        done, _pending = await asyncio.wait({task}, timeout=SSE_KEEPALIVE_INTERVAL_SECONDS)
        if not done:
            for frame in iter_stream_keepalive_frames(encoder, phase):
                yield frame


def _record_emitted_text_signatures(encoded_events: list[str], signatures: set[str]) -> str:
    """从已编码的 SSE 事件里登记正文指纹。

    `_emit_assistant_text_message` 会把长文拆成多段 TEXT_MESSAGE_CONTENT；
    若只登记各段 delta，后续 on_chain_end 用整段 AIMessage.content 比对会落空，
    再把同一份回答发一遍。这里同时登记分段与拼接后的全文。
    """
    parts: list[str] = []
    for ev in encoded_events or []:
        if "TEXT_MESSAGE_CONTENT" not in ev:
            continue
        try:
            payload = json.loads(ev.split("data: ", 1)[1])
        except (json.JSONDecodeError, IndexError):
            continue
        content = payload.get("delta") or ""
        if not content:
            continue
        signatures.add(content)
        parts.append(content)
    full = "".join(parts)
    if full:
        signatures.add(full)
    return full


def _is_hidden_builtin_tool(tool_name: str) -> bool:
    """该工具是否为应在 AG-UI 流中隐藏的 deepagents 内置工具。"""
    import os

    if os.getenv("OPSPILOT_AGUI_SHOW_BUILTIN_TOOLS", "0") == "1":
        return False
    return tool_name in _DEEPAGENT_BUILTIN_TOOL_NAMES


# Sensitive field patterns for masking in SSE events (logging/frontend display only)
_SENSITIVE_FIELD_PATTERNS = frozenset(
    {
        "password",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "credential",
        "auth",
        "密码",
        "口令",
        "秘钥",
    }
)


def _mask_sensitive_data(data: Any) -> Any:
    """
    Mask sensitive data in tool arguments for SSE event output.

    This function creates a deep copy and masks values of sensitive fields
    (password, token, secret, etc.) to prevent credential leakage in logs/frontend.

    NOTE: This is ONLY for display purposes. The original data passed to
    tool execution remains unchanged.

    Args:
        data: The data to mask (dict, list, or primitive)

    Returns:
        A copy with sensitive values replaced by "***"
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            # Check if any sensitive pattern is contained in the key
            is_sensitive = any(pattern in key_lower for pattern in _SENSITIVE_FIELD_PATTERNS)
            if is_sensitive and isinstance(value, str) and value:
                result[key] = "***"
            else:
                result[key] = _mask_sensitive_data(value)
        return result
    elif isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    else:
        return data


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
        except Exception as exc:
            # 必须显式上报：create_task 的异常否则会被 finally 里 await 静默吞掉，
            # 表现为「问答无输出 / RUN_FINISHED 空跑」。
            await output_queue.put(("langgraph_error", exc))
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
                logger.exception(f"Browser event consumer error: {e}")
                break

    # 启动两个并发消费者
    langgraph_task = asyncio.create_task(langgraph_consumer())
    browser_task = asyncio.create_task(browser_event_consumer())

    langgraph_done = False
    langgraph_error: Optional[BaseException] = None
    idle_seconds = 0.0
    queue_wait_seconds = 0.1

    try:
        while True:
            try:
                # 从合并队列获取事件
                event_type, data = await asyncio.wait_for(output_queue.get(), timeout=queue_wait_seconds)
                idle_seconds = 0.0

                if event_type == "langgraph_error":
                    langgraph_error = data if isinstance(data, BaseException) else RuntimeError(str(data))
                    continue
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
                idle_seconds += queue_wait_seconds
                if idle_seconds >= SSE_KEEPALIVE_INTERVAL_SECONDS:
                    idle_seconds = 0.0
                    yield ("keepalive", "waiting_model")
                continue

        if langgraph_error is not None:
            raise langgraph_error

    finally:
        # 清理: 设置停止信号并取消任务
        stop_event.set()
        browser_task.cancel()

        # 等待任务完成。旧逻辑 `except Exception: pass` 会吞掉轻量直答/节点内
        # LLM 失败，表现为 RUN_STARTED→RUN_FINISHED、无正文、llm_call_count=0。
        try:
            await langgraph_task
        except Exception as e:
            langgraph_error = e

        try:
            await browser_task
        except asyncio.CancelledError:
            pass

    if langgraph_error is not None:
        raise langgraph_error


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
                    # 包含 screenshot 供人工查看调试，不经过 LLM，无额外 token 消耗
                    "screenshot": step_info.get("screenshot"),
                },
            )

            # 编码并推送到队列（非阻塞）
            encoded_event = encoder.encode(event)
            try:
                event_queue.put_nowait(encoded_event)
            except asyncio.QueueFull:
                logger.warning("Browser step event queue is full, dropping event")

        except Exception as e:
            logger.exception(f"Error in browser step callback: {e}")

    return step_callback


def create_browser_custom_event_callback(
    event_queue: asyncio.Queue,
    encoder: EventEncoder,
) -> Callable[[Dict[str, Any]], None]:
    """创建浏览器自定义事件回调函数，用于发送 browser_task_received 等事件"""

    def custom_event_callback(event_value: Dict[str, Any]) -> None:
        try:
            event = CustomEvent(
                type=EventType.CUSTOM,
                name="browser_task_received",
                value=event_value,
            )
            encoded_event = encoder.encode(event)
            try:
                event_queue.put_nowait(encoded_event)
            except asyncio.QueueFull:
                logger.warning("Browser custom event queue is full, dropping event")
        except Exception as e:
            logger.exception(f"Error in browser custom event callback: {e}")

    return custom_event_callback


class BasicGraph(ABC):
    """基础图执行类，提供流式和非流式执行能力"""

    def prepare_graph(self, graph_builder, node_builder) -> str:
        """准备基础图结构，添加节点和边"""
        graph_builder.add_node("prompt_message_node", node_builder.prompt_message_node)
        graph_builder.add_node("add_chat_history_node", node_builder.add_chat_history_node)
        graph_builder.add_node("user_message_node", node_builder.user_message_node)
        graph_builder.add_node("suggest_question_node", node_builder.suggest_question_node)

        graph_builder.add_edge(START, "prompt_message_node")
        graph_builder.add_edge("prompt_message_node", "suggest_question_node")
        graph_builder.add_edge("suggest_question_node", "add_chat_history_node")
        graph_builder.add_edge("add_chat_history_node", "user_message_node")

        return "user_message_node"

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
            "recursion_limit": 100,
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

    def _extract_content_from_chunk(self, content: Any) -> tuple[str, str]:
        """从 chunk.content 中提取文本内容和 thinking 内容

        Anthropic 格式的 content 可能是:
        - str: 普通文本
        - list: 包含 content blocks，如 [{'type': 'thinking', 'thinking': '...'}, {'type': 'text', 'text': '...'}]

        Returns:
            (text_content, thinking_content)
        """
        if isinstance(content, str):
            return content, ""

        if not isinstance(content, list):
            return str(content), ""

        text_parts = []
        thinking_parts = []

        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue

            block_type = block.get("type", "")

            # Anthropic thinking block 格式
            if block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    thinking_parts.append(thinking_text)
            # Anthropic text block 格式
            elif block_type == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)
            # 其他格式，尝试提取 text 或转为字符串
            elif "text" in block:
                text_parts.append(block["text"])
            elif "content" in block:
                text_parts.append(str(block["content"]))

        return "".join(text_parts), "".join(thinking_parts)

    def _emit_assistant_text_message(self, encoder: EventEncoder, text: str) -> list[str]:
        """把一整段助手正文编码为 TEXT_MESSAGE_START/CONTENT*/END（长文拆多段 CONTENT）。"""
        text = str(text or "")
        if not text:
            return []
        msg_id = str(uuid.uuid4())
        events = [
            encoder.encode(
                TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    message_id=msg_id,
                    role="assistant",
                    timestamp=int(time.time() * 1000),
                )
            )
        ]
        for piece in _split_text_deltas(text):
            events.append(
                encoder.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=msg_id,
                        delta=piece,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
        events.append(
            encoder.encode(
                TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=msg_id,
                    timestamp=int(time.time() * 1000),
                )
            )
        )
        return events

    def _emit_live_text_delta(
        self,
        encoder: EventEncoder,
        run_id: str,
        text: str,
        *,
        message_id: Optional[str],
        message_started: bool,
    ) -> tuple[list[str], Optional[str], bool]:
        """实时追加正文 delta；必要时先发 TEXT_MESSAGE_START；过长则拆多段。"""
        text = str(text or "")
        if not text:
            return [], message_id, message_started
        events: list[str] = []
        if not message_started or not message_id:
            message_id = f"msg_{run_id}_{int(time.time() * 1000)}"
            message_started = True
            events.append(
                encoder.encode(
                    TextMessageStartEvent(
                        type=EventType.TEXT_MESSAGE_START,
                        message_id=message_id,
                        role="assistant",
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
        for piece in _split_text_deltas(text):
            events.append(
                encoder.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=message_id,
                        delta=piece,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
        return events, message_id, message_started

    def _handle_chat_model_stream_content(
        self,
        chunk: Any,
        encoder: EventEncoder,
        run_id: str,
        current_message_id: Optional[str],
        message_started: bool,
        show_think: bool,
        thinking_started: bool,
        text_strip_buffers: Optional[Dict[str, str]] = None,
        emit_text: bool = True,
    ) -> tuple[list[str], Optional[str], bool, bool, str]:
        """处理 on_chat_model_stream 事件中的文本内容

        text_strip_buffers: per-message_id 的 tail 缓冲,用于跨 streaming chunk 的
        phantom tool call strip。LLM 把 <tool_call>name{ar | gs}</tool_call> 拆成两个 chunk
        时,per-chunk strip 抓不到闭合配对;buffer 方式把上一 chunk 末尾 N 字符留到下
        一 chunk 拼回去再 strip,跨 chunk 也能抹掉。

        emit_text: False 时不推送 TEXT_MESSAGE_*（供 agui_stream 按轮次缓冲，避免工具旁白泄漏），
        仍推送 thinking，并把本应作为正文的文本经第 5 个返回值交还给调用方。

        Returns:
            (events, message_id, message_started, thinking_started, buffered_text_delta)
        """
        events = []
        buffered_text = ""
        if not (chunk and hasattr(chunk, "content")):
            return events, current_message_id, message_started, thinking_started, buffered_text

        # 处理 Anthropic 格式的 content（可能是 list of content blocks）
        content_delta, thinking_delta = self._extract_content_from_chunk(chunk.content)

        # LLM 偶尔会走错格式把"想调的工具"写成 <tool_call>name{args}</tool_call> 或
        # <|tool_call|>...<|tool_call|>,但 deepagent 不解析这些 XML 模式,所以这些
        # 根本没执行,只是 LLM 在 text 里假装调了。strip 掉避免前端渲染成"伪工具记录"。
        # 真实工具调用走 TOOL_CALL_START 事件通道,不在 text content 里,strip 不影响。
        # 跨 chunk 处理:把上一 chunk 末尾的 tail 拼到本 chunk,strip 完整 phantom call。
        # 如果还有未闭合的 phantom call 起始,把那部分留到下一 chunk 才 emit;
        # 闭合完整就 emit 全部。
        if content_delta and text_strip_buffers is not None and current_message_id:
            # message_id 切换时清掉旧 message 的 tail(消息已结束,tail 永远不会被它的
            # 下一 chunk 关闭,留着只是占内存)
            for mid in list(text_strip_buffers.keys()):
                if mid != current_message_id:
                    text_strip_buffers.pop(mid, None)
            tail = text_strip_buffers.get(current_message_id, "")
            buffered = tail + content_delta
            cleaned = strip_phantom_tool_calls(buffered)
            unclosed_start = find_unclosed_phantom_tool_call_start(cleaned)
            if unclosed_start is not None:
                # 末尾有未闭合 phantom,从起点开始 hold
                content_delta = cleaned[:unclosed_start]
                text_strip_buffers[current_message_id] = cleaned[unclosed_start:]
            else:
                # 全部闭合(phantom 被完整 strip 或本来就没有),emit 全部
                content_delta = cleaned
                text_strip_buffers.pop(current_message_id, None)
        elif content_delta:
            # 没有 buffer 上下文(老调用路径),per-chunk strip,够覆盖单 chunk 完整 phantom
            content_delta = strip_phantom_tool_calls(content_delta)

        # 从 additional_kwargs 中提取 reasoning_content（DeepSeek/Gemma 等通过 vLLM
        # reasoning-parser 暴露的推理内容，lc_patches.py 已统一归到此字段）
        if not thinking_delta:
            rc = (getattr(chunk, "additional_kwargs", None) or {}).get("reasoning_content", "")
            if rc:
                thinking_delta = rc

        if not chunk.content and not thinking_delta:
            return events, current_message_id, message_started, thinking_started, buffered_text

        # 处理 thinking 内容（Anthropic 格式 / vLLM reasoning-parser 格式）
        if thinking_delta and show_think:
            if not thinking_started:
                thinking_started = True
                events.append(
                    encoder.encode(
                        ThinkingTextMessageStartEvent(
                            type=EventType.THINKING_TEXT_MESSAGE_START,
                            message_id=f"think_{run_id}_{int(time.time() * 1000)}",
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
            events.append(
                encoder.encode(
                    ThinkingTextMessageContentEvent(
                        type=EventType.THINKING_TEXT_MESSAGE_CONTENT,
                        delta=thinking_delta,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )

        # 如果没有文本内容，直接返回
        if not content_delta:
            return events, current_message_id, message_started, thinking_started, buffered_text

        def _append_plain_text(plain: str) -> None:
            nonlocal current_message_id, message_started, buffered_text
            if not plain:
                return
            if not emit_text:
                buffered_text += plain
                return
            if not message_started:
                current_message_id = f"msg_{run_id}_{int(time.time() * 1000)}"
                message_started = True
                events.append(
                    encoder.encode(
                        TextMessageStartEvent(
                            type=EventType.TEXT_MESSAGE_START,
                            message_id=current_message_id,
                            role="assistant",
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
            events.append(
                encoder.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=current_message_id,
                        delta=plain,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )

        if show_think:
            remaining_content = content_delta
            while remaining_content:
                think_start = remaining_content.find("<think>")
                if think_start == -1:
                    _append_plain_text(remaining_content)
                    break

                plain_prefix = remaining_content[:think_start]
                _append_plain_text(plain_prefix)

                remaining_content = remaining_content[think_start + len("<think>") :]
                think_end = remaining_content.find("</think>")

                if not thinking_started:
                    thinking_started = True
                    events.append(
                        encoder.encode(
                            ThinkingTextMessageStartEvent(
                                type=EventType.THINKING_TEXT_MESSAGE_START,
                                timestamp=int(time.time() * 1000),
                            )
                        )
                    )

                if think_end == -1:
                    if remaining_content:
                        events.append(
                            encoder.encode(
                                ThinkingTextMessageContentEvent(
                                    type=EventType.THINKING_TEXT_MESSAGE_CONTENT,
                                    delta=remaining_content,
                                )
                            )
                        )
                    remaining_content = ""
                else:
                    think_content = remaining_content[:think_end]
                    if think_content:
                        events.append(
                            encoder.encode(
                                ThinkingTextMessageContentEvent(
                                    type=EventType.THINKING_TEXT_MESSAGE_CONTENT,
                                    delta=think_content,
                                )
                            )
                        )
                    events.append(
                        encoder.encode(
                            ThinkingTextMessageEndEvent(
                                type=EventType.THINKING_TEXT_MESSAGE_END,
                                timestamp=int(time.time() * 1000),
                            )
                        )
                    )
                    thinking_started = False
                    remaining_content = remaining_content[think_end + len("</think>") :]

            return events, current_message_id, message_started, thinking_started, buffered_text

        _append_plain_text(content_delta)
        return events, current_message_id, message_started, thinking_started, buffered_text

    def _handle_tool_call_chunks(
        self,
        chunk: Any,
        encoder: EventEncoder,
        current_message_id: Optional[str],
        current_tool_calls: Dict[str, Dict],
    ) -> list[str]:
        """处理 on_chat_model_stream 事件中的流式工具调用"""
        events = []
        if not (chunk and hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks):
            return events

        for tool_chunk in chunk.tool_call_chunks:
            tool_call_id = tool_chunk.get("id")
            if tool_call_id and tool_call_id not in current_tool_calls:
                tool_name = tool_chunk.get("name", "unknown")
                current_tool_calls[tool_call_id] = {"name": tool_name, "started": True}
                events.append(
                    encoder.encode(
                        ToolCallStartEvent(
                            type=EventType.TOOL_CALL_START,
                            tool_call_id=tool_call_id,
                            tool_call_name=tool_name,
                            parent_message_id=current_message_id,
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
        return events

    def _handle_tool_start_event(
        self,
        event: Dict[str, Any],
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_message_id: Optional[str],
        current_tool_calls: Dict[str, Dict],
    ) -> list[str]:
        """处理 on_tool_start 事件"""
        events = []
        tool_name = event.get("name", "unknown")
        # 隐藏 deepagents 内置工具（规划/文件系统/子代理），保持前端体验一致。
        # 跳过 start 后，对应的 tool_end 因找不到已登记的 tool_call_id 自然 no-op。
        if _is_hidden_builtin_tool(tool_name):
            return events
        tool_input = event_data.get("input", {})
        run_id_from_event = event.get("run_id", "")
        normalized_tool_input = self._normalize_tool_match_payload(tool_input)

        # 查找已存在的相同工具名的未结束调用
        existing_tool_call_id = None
        for tid, tinfo in current_tool_calls.items():
            if tinfo.get("name") == tool_name and not tinfo.get("ended") and not tinfo.get("tool_started"):
                existing_tool_call_id = tid
                tinfo["tool_started"] = True
                tinfo["run_id"] = run_id_from_event
                break

        # LangGraph 实际工具事件名可能是 RunnableCallable 等包装名，而模型 tool_call 名仍是 execute。
        # 此时按参数匹配，把实际执行结果绑定回模型声明的工具调用，避免前端看到“未收到结果事件”。
        if not existing_tool_call_id and normalized_tool_input:
            for tid, tinfo in current_tool_calls.items():
                if tinfo.get("ended") or tinfo.get("tool_started"):
                    continue
                if self._normalize_tool_match_payload(tinfo.get("args")) == normalized_tool_input:
                    existing_tool_call_id = tid
                    tinfo["tool_started"] = True
                    tinfo["run_id"] = run_id_from_event
                    break

        if not existing_tool_call_id:
            pending_tool_call_ids = [tid for tid, tinfo in current_tool_calls.items() if not tinfo.get("ended") and not tinfo.get("tool_started")]
            if len(pending_tool_call_ids) == 1:
                existing_tool_call_id = pending_tool_call_ids[0]
                current_tool_calls[existing_tool_call_id]["tool_started"] = True
                current_tool_calls[existing_tool_call_id]["run_id"] = run_id_from_event

        if existing_tool_call_id:
            if tool_input:
                # Mask sensitive data (password, token, etc.) for SSE output only
                masked_input = _mask_sensitive_data(tool_input) if isinstance(tool_input, dict) else tool_input
                events.append(
                    encoder.encode(
                        ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=existing_tool_call_id,
                            delta=json.dumps(masked_input, ensure_ascii=False) if isinstance(masked_input, dict) else str(masked_input),
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
        else:
            tool_call_id = f"tool_{run_id_from_event}" if run_id_from_event else f"tool_{uuid.uuid4()}"
            current_tool_calls[tool_call_id] = {
                "name": tool_name,
                "started": True,
                "tool_started": True,
                "run_id": run_id_from_event,
            }
            events.append(
                encoder.encode(
                    ToolCallStartEvent(
                        type=EventType.TOOL_CALL_START,
                        tool_call_id=tool_call_id,
                        tool_call_name=tool_name,
                        parent_message_id=current_message_id,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
            if tool_input:
                # Mask sensitive data (password, token, etc.) for SSE output only
                masked_input = _mask_sensitive_data(tool_input) if isinstance(tool_input, dict) else tool_input
                events.append(
                    encoder.encode(
                        ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=tool_call_id,
                            delta=json.dumps(masked_input, ensure_ascii=False) if isinstance(masked_input, dict) else str(masked_input),
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
        return events

    @staticmethod
    def _normalize_tool_match_payload(value: Any) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _normalize_tool_result_content(tool_output: Any) -> str:
        """把 on_tool_end 的 output 规范成可展示的工具结果字符串。"""
        if tool_output is None or tool_output == "":
            return ""
        if isinstance(tool_output, ToolMessage):
            return str(getattr(tool_output, "content", "") or "")
        # 部分运行时会把 ToolMessage 包在带 content 属性的容器里
        content_attr = getattr(tool_output, "content", None)
        if content_attr is not None and not isinstance(tool_output, (str, bytes, dict, list, tuple, int, float, bool)):
            return str(content_attr or "")
        return str(tool_output)

    def _handle_tool_end_event(
        self,
        event: Dict[str, Any],
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
    ) -> list[str]:
        """处理 on_tool_end 事件"""
        events = []
        tool_name = event.get("name", "unknown")
        tool_output = event_data.get("output", "")
        run_id_from_event = event.get("run_id", "")

        # 优先使用 run_id 匹配
        tool_call_id = None
        for tid, tinfo in current_tool_calls.items():
            if tinfo.get("run_id") == run_id_from_event and not tinfo.get("ended"):
                tool_call_id = tid
                tinfo["ended"] = True
                break

        # 用 tool_name 兜底
        if not tool_call_id:
            for tid, tinfo in current_tool_calls.items():
                if tinfo.get("name") == tool_name and not tinfo.get("ended"):
                    tool_call_id = tid
                    tinfo["ended"] = True
                    break

        if tool_call_id:
            events.append(
                encoder.encode(
                    ToolCallEndEvent(
                        type=EventType.TOOL_CALL_END,
                        tool_call_id=tool_call_id,
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
            events.append(
                encoder.encode(
                    ToolCallResultEvent(
                        type=EventType.TOOL_CALL_RESULT,
                        message_id=f"result_{uuid.uuid4()}",
                        tool_call_id=tool_call_id,
                        content=self._normalize_tool_result_content(tool_output),
                        role="tool",
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
            # 标记已回填，避免后续 on_chain_end 用同一 ToolMessage 再发一遍 RESULT
            current_tool_calls[tool_call_id]["result_sent"] = True
        return events

    @staticmethod
    def _unwrap_overwrite_messages(messages):
        """兼容 LangGraph Overwrite(messages) 包装，返回实际消息列表。"""
        if messages.__class__.__name__ == "Overwrite" and hasattr(messages, "value"):
            return messages.value or []
        return messages

    def _resolve_tool_call_meta_from_messages(self, messages: list, tool_call_id: str, tool_message: ToolMessage) -> tuple[str, Any]:
        """从同批 messages 里的 AIMessage.tool_calls 还原工具名与参数。"""
        tool_name = str(getattr(tool_message, "name", "") or "").strip() or "unknown"
        tool_args: Any = None
        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            for tool_call in getattr(message, "tool_calls", None) or []:
                if hasattr(tool_call, "get"):
                    tid = tool_call.get("id")
                    name = tool_call.get("name")
                    args = tool_call.get("args")
                else:
                    tid = getattr(tool_call, "id", None)
                    name = getattr(tool_call, "name", None)
                    args = getattr(tool_call, "args", None)
                if tid == tool_call_id:
                    if name:
                        tool_name = str(name)
                    tool_args = args
                    return tool_name, tool_args
        return tool_name, tool_args

    def _ensure_tool_call_events_for_tool_message(
        self,
        tool_message: ToolMessage,
        messages: list,
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
    ) -> list[str]:
        """ToolMessage 尚未对应 TOOL_CALL_START 时补发 START/ARGS（DeepAgent 嵌套常见）。"""
        tool_call_id = str(getattr(tool_message, "tool_call_id", "") or "").strip()
        if not tool_call_id or tool_call_id in current_tool_calls:
            return []

        tool_name, tool_args = self._resolve_tool_call_meta_from_messages(messages, tool_call_id, tool_message)
        if _is_hidden_builtin_tool(tool_name):
            return []

        current_tool_calls[tool_call_id] = {
            "name": tool_name,
            "started": True,
            "tool_started": True,
        }
        events = [
            encoder.encode(
                ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=tool_call_id,
                    tool_call_name=tool_name,
                    parent_message_id=None,
                    timestamp=int(time.time() * 1000),
                )
            )
        ]
        if tool_args not in (None, "", {}, []):
            masked_args = _mask_sensitive_data(tool_args) if isinstance(tool_args, dict) else tool_args
            events.append(
                encoder.encode(
                    ToolCallArgsEvent(
                        type=EventType.TOOL_CALL_ARGS,
                        tool_call_id=tool_call_id,
                        delta=json.dumps(masked_args, ensure_ascii=False) if isinstance(masked_args, dict) else str(masked_args),
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
        return events

    def _emit_tool_result_events_from_messages(
        self,
        messages: list,
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
    ) -> tuple[list[str], bool, Optional[AIMessage]]:
        """遍历 messages，补齐缺失的工具 START，并回填 RESULT。

        返回的 AIMessage 优先取「工具结果之后」的最终回答。无工具时只在
        **当前列表以该 AIMessage 结尾** 时回退为轻量直答正文；历史加载 /
        prepare 子链结束时列表以 HumanMessage 结尾，不得把上一轮助手回复
        当成本轮输出。
        """
        events: list[str] = []
        emitted_tool_result = False
        latest_ai_message_after_tool_result: Optional[AIMessage] = None
        latest_plain_ai_message: Optional[AIMessage] = None

        for message in messages:
            if isinstance(message, AIMessage):
                if getattr(message, "content", "") or "":
                    latest_plain_ai_message = message
                if emitted_tool_result and (getattr(message, "content", "") or ""):
                    latest_ai_message_after_tool_result = message
                continue

            if not isinstance(message, ToolMessage):
                continue

            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if not tool_call_id:
                continue

            events.extend(
                self._ensure_tool_call_events_for_tool_message(
                    message,
                    messages,
                    encoder,
                    current_tool_calls,
                )
            )
            if tool_call_id not in current_tool_calls:
                continue

            tool_info = current_tool_calls[tool_call_id]
            if tool_info.get("result_sent"):
                continue

            if not tool_info.get("ended"):
                events.append(
                    encoder.encode(
                        ToolCallEndEvent(
                            type=EventType.TOOL_CALL_END,
                            tool_call_id=tool_call_id,
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
                tool_info["ended"] = True

            events.append(
                encoder.encode(
                    ToolCallResultEvent(
                        type=EventType.TOOL_CALL_RESULT,
                        message_id=f"result_{uuid.uuid4()}",
                        tool_call_id=tool_call_id,
                        content=str(getattr(message, "content", "") or ""),
                        role="tool",
                        timestamp=int(time.time() * 1000),
                    )
                )
            )
            tool_info["result_sent"] = True
            emitted_tool_result = True
            latest_ai_message_after_tool_result = None

        if latest_ai_message_after_tool_result is None and not emitted_tool_result:
            last_message = messages[-1] if messages else None
            if last_message is latest_plain_ai_message:
                latest_ai_message_after_tool_result = latest_plain_ai_message

        return events, emitted_tool_result, latest_ai_message_after_tool_result

    def _handle_chain_end_messages(
        self,
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
        include_text: bool = True,
    ) -> list[str]:
        """把节点结束时返回的 LangChain messages 补成 AG-UI 事件。

        DeepAgent 会在内部执行工具，外层 LangGraph 不一定逐个抛出 on_tool_end。
        这时工具结果只存在于节点 output.messages 的 ToolMessage 中，需要在这里
        回填成 TOOL_CALL_START/RESULT，否则前端步骤详情会显示「本步无工具调用」。
        """
        output = event_data.get("output")
        messages = []
        if isinstance(output, dict):
            messages = output.get("messages") or []
        elif hasattr(output, "get"):
            messages = output.get("messages") or []
        elif hasattr(output, "messages"):
            messages = getattr(output, "messages") or []

        messages = self._unwrap_overwrite_messages(messages)
        if not messages:
            return []

        events, _, latest_ai_message_after_tool_result = self._emit_tool_result_events_from_messages(
            messages,
            encoder,
            current_tool_calls,
        )

        if include_text and latest_ai_message_after_tool_result is not None:
            for ev in self._handle_chat_model_end_event(
                {"output": latest_ai_message_after_tool_result},
                encoder,
                None,
                current_tool_calls,
                message_started=False,
                allow_non_streaming_text=True,
            ):
                events.append(ev)

        return events

    def _handle_chain_end_tool_results_only(
        self,
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
    ) -> list[str]:
        """只回填 chain_end 里的 ToolMessage 结果,不重发 AI 文本。

        当本轮 on_chat_model_end 已经 emit 过非流式 AI 文本时,需要这个变体
        避免链尾再把同一份文本推一遍;但 ToolMessage 仍要补成 TOOL_CALL_RESULT,
        否则前端的 tool_call 会停留在"未收到结果"。
        """
        return self._handle_chain_end_messages(event_data, encoder, current_tool_calls, include_text=False)

    def _handle_chain_end_messages_dedup(
        self,
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_tool_calls: Dict[str, Dict],
        emitted_text_signatures: set[str],
    ) -> list[str]:
        """_handle_chain_end_messages 的去重包装:跳过已发过同内容的 AI 文本。

        emit 顺序:ToolMessage 补发照常;最新的 AI 文本若在 emitted_text_signatures
        里就跳过,避免 on_chat_model_end 已经发过的最终回答被父/子图的 chain_end
        重复 emit。
        """
        output = event_data.get("output")
        messages = []
        if isinstance(output, dict):
            messages = output.get("messages") or []
        elif hasattr(output, "get"):
            messages = output.get("messages") or []
        elif hasattr(output, "messages"):
            messages = getattr(output, "messages") or []

        messages = self._unwrap_overwrite_messages(messages)
        if not messages:
            return []

        events, _, latest_ai_message_after_tool_result = self._emit_tool_result_events_from_messages(
            messages,
            encoder,
            current_tool_calls,
        )

        if latest_ai_message_after_tool_result is not None:
            content = str(getattr(latest_ai_message_after_tool_result, "content", "") or "")
            # 关键:若这份文本 chat_model_end 或更早的 chain_end 已经发过,跳过 emit
            if content and content in emitted_text_signatures:
                return events
            for ev in self._handle_chat_model_end_event(
                {"output": latest_ai_message_after_tool_result},
                encoder,
                None,
                current_tool_calls,
                message_started=False,
                allow_non_streaming_text=True,
                emitted_text_signatures=emitted_text_signatures,
            ):
                events.append(ev)

        return events

    def _handle_chat_model_end_event(
        self,
        event_data: Dict[str, Any],
        encoder: EventEncoder,
        current_message_id: Optional[str],
        current_tool_calls: Dict[str, Dict],
        message_started: bool = False,
        allow_non_streaming_text: bool = False,
        fallback_text: str = "",
        emitted_text_signatures: Optional[set[str]] = None,
    ) -> list[str]:
        """处理 on_chat_model_end 事件：补充文本输出（非流式 adapter）和工具调用"""
        events = []
        output = event_data.get("output")
        if not output:
            return events

        # 非流式 adapter（如 AnthropicCompatibleChatClient）不产生 on_chat_model_stream，
        # 文本内容只出现在 on_chat_model_end。必须确认 message_started 为 False，
        # 否则流式 adapter 已经推送过文本，重复 emit 会导致前端显示两遍内容。
        text_content = getattr(output, "content", "") or ""
        # 跟 streaming 同样的处理:剥 LLM 幻觉的 XML 工具调用
        text_content = strip_phantom_tool_calls(text_content)
        if not text_content and fallback_text:
            text_content = strip_phantom_tool_calls(fallback_text)
        tool_calls_list = getattr(output, "tool_calls", None) or []
        if text_content and not tool_calls_list and (not message_started or allow_non_streaming_text):
            # DeepAgent 步骤内确认文案 + 步骤后再来一轮相同正文时，指纹去重只推一次。
            if emitted_text_signatures is not None and text_content in emitted_text_signatures:
                return events
            events.extend(self._emit_assistant_text_message(encoder, text_content))
            if emitted_text_signatures is not None:
                emitted_text_signatures.add(text_content)
            return events

        # 工具调用：补充未经 on_chat_model_stream 发出的 tool_call 事件
        if not tool_calls_list:
            return events

        for tool_call in tool_calls_list:
            if hasattr(tool_call, "get"):
                tool_call_id = tool_call.get("id") or f"tool_{uuid.uuid4()}"
                tool_name = tool_call.get("name", "unknown")
                tool_args = tool_call.get("args")
            else:
                tool_call_id = getattr(tool_call, "id", None) or f"tool_{uuid.uuid4()}"
                tool_name = getattr(tool_call, "name", "unknown")
                tool_args = getattr(tool_call, "args", None)

            # 隐藏 deepagents 内置工具的调用事件
            if _is_hidden_builtin_tool(tool_name):
                continue

            if tool_call_id not in current_tool_calls:
                current_tool_calls[tool_call_id] = {"name": tool_name, "started": True, "args": tool_args}
                events.append(
                    encoder.encode(
                        ToolCallStartEvent(
                            type=EventType.TOOL_CALL_START,
                            tool_call_id=tool_call_id,
                            tool_call_name=tool_name,
                            parent_message_id=current_message_id,
                            timestamp=int(time.time() * 1000),
                        )
                    )
                )
                if tool_args:
                    masked_args = _mask_sensitive_data(tool_args) if isinstance(tool_args, dict) else tool_args
                    events.append(
                        encoder.encode(
                            ToolCallArgsEvent(
                                type=EventType.TOOL_CALL_ARGS,
                                tool_call_id=tool_call_id,
                                delta=json.dumps(masked_args, ensure_ascii=False) if isinstance(masked_args, dict) else str(masked_args),
                                timestamp=int(time.time() * 1000),
                            )
                        )
                    )
            else:
                current_tool_calls[tool_call_id]["args"] = tool_args
        return events

    async def agui_stream(  # noqa: C901
        self,
        request: BasicLLMRequest,
        token_usage_accumulator: Optional[TokenUsageAccumulator] = None,
    ) -> AsyncGenerator[str, None]:
        """
        使用 agui 协议以 SSE 格式流式输出事件

        使用 astream_events(version="v2") 获取细粒度的流式事件，实现真正的 token-by-token 输出。
        支持浏览器工具执行进度的实时流式推送。

        Args:
            request: 基础 LLM 请求对象
            token_usage_accumulator: 可选的整轮 LLM token 用量聚合器

        Yields:
            SSE 格式的事件字符串: "data: {json}\\n\\n"
        """
        encoder = EventEncoder()
        run_id = str(uuid.uuid4())
        thread_id = request.thread_id or str(uuid.uuid4())
        current_message_id: Optional[str] = None
        current_tool_calls: Dict[str, Dict] = {}
        message_started = False
        thinking_started = False
        tool_result_seen_since_model_end = False
        # 本轮模型输出的正文缓冲：
        # - 见 tool_call 前先缓冲；一旦出现 tool_call 则丢弃（旁白不进正文）
        # - 连续多个正文 chunk 仍无 tool_call → 判定为纯文本轮，开始实时推送
        # - 仅 1 个短 chunk 后就 tool_call 的旁白轮：全程不推正文
        pending_turn_text = ""
        turn_saw_tool_call_chunks = False
        turn_plain_text_chunks = 0
        turn_text_live = False
        live_turn_emitted_text = ""
        pending_turn_strip_key = "__pending_turn__"
        output_truncated = False
        # 跨 streaming chunk 的 phantom tool call strip buffer。
        # key = message_id,value = 该 message 累积的未 emit tail。
        # 当 message_id 变化时清理旧 entry(消息结束 → 它的 tail 不再有用了)。
        text_strip_buffers: Dict[str, str] = {}
        # DeepAgent 场景下,on_chat_model_end 携带完整 AI 文本(allow_non_streaming_text=True
        # 时)与 on_chain_end 的 output.messages 里的同一份 AIMessage 会重复 emit。
        # 而且父/子图会多次触发 on_chain_end,都带同一份文本,所以用内容指纹去重:
        # 任何源 emit 过这份文本后,后续 chain_end 再遇到相同内容就跳过。
        # 注意:长文会被拆成多段 delta,必须同时登记「全文」指纹,否则 chain_end
        # 用整段 content 比对会落空,前端就会看到同一段回答出现两次。
        # 指纹只登记本轮实际发出的正文，不得预填历史助手文本：否则本轮短句
        # 若与上一轮相同（如「好的」）会被静默丢掉。历史重放靠节点名 /
        # last_message is latest_plain_ai_message 拦截。
        emitted_text_signatures: set[str] = set()
        emitted_any_text_this_run = False
        show_think = bool((request.extra_config or {}).get("show_think", True))
        execution_id = (request.extra_config or {}).get("execution_id") or request.thread_id
        if not isinstance(token_usage_accumulator, TokenUsageAccumulator):
            token_usage_accumulator = None
        # 创建浏览器步骤事件队列和回调
        browser_event_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        browser_step_callback = create_browser_step_callback(browser_event_queue, encoder)
        browser_custom_event_callback = create_browser_custom_event_callback(browser_event_queue, encoder)
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
            for frame in iter_stream_keepalive_frames(encoder, "started"):
                yield frame

            compile_task = asyncio.ensure_future(self.compile_graph(request))
            async for keepalive in iter_sse_keepalive_until(compile_task, encoder, "compile_graph"):
                yield keepalive
            graph = compile_task.result()
            if graph is None:
                raise RuntimeError("Failed to compile graph: graph is None")

            config = {
                "recursion_limit": 100,
                "trace_id": str(uuid.uuid4()),
                "configurable": {
                    "graph_request": request,
                    "user_id": request.user_id or "",
                    **request.extra_config,
                    "browser_step_callback": browser_step_callback,
                    "browser_custom_event_callback": browser_custom_event_callback,
                    "token_usage_accumulator": token_usage_accumulator,
                },
            }

            langgraph_stream = graph.astream_events(
                {"messages": [], "graph_request": request},
                config=config,
                version="v2",
            )

            async for stream_type, stream_data in _merge_async_streams(langgraph_stream, browser_event_queue, stop_event):
                if stream_type == "keepalive":
                    for frame in iter_stream_keepalive_frames(encoder, str(stream_data or "waiting_model")):
                        yield frame
                    continue
                if execution_id and await is_interrupt_requested_async(execution_id):
                    yield encoder.encode(
                        RunErrorEvent(
                            type=EventType.RUN_ERROR,
                            message="执行已中断",
                            code="INTERRUPTED",
                            timestamp=int(time.time() * 1000),
                        )
                    )
                    return
                if stream_type == "browser":
                    yield stream_data
                    continue

                event = stream_data
                event_type = event.get("event")
                event_data = event.get("data", {})

                if event_type == "on_chat_model_stream":
                    chunk = event_data.get("chunk")
                    chunk_metadata = dict(getattr(chunk, "response_metadata", {}) or {})
                    chunk_reason = str(chunk_metadata.get("finish_reason") or chunk_metadata.get("stop_reason") or "").casefold()
                    if chunk_reason in {"length", "max_tokens", "max_output_tokens", "token_limit"}:
                        output_truncated = True

                    # 先看 tool_call：同 chunk 内工具优先于正文，避免旁白泄漏。
                    tool_chunk_events = self._handle_tool_call_chunks(chunk, encoder, current_message_id, current_tool_calls)
                    if tool_chunk_events:
                        # 若旁白已提前开播，先撤回再发工具事件。
                        if live_turn_emitted_text and current_message_id:
                            yield encoder.encode(
                                CustomEvent(
                                    type=EventType.CUSTOM,
                                    name="assistant_text_retract",
                                    value={"message_id": current_message_id, "reason": "tool_call"},
                                )
                            )
                            if message_started:
                                yield encoder.encode(
                                    TextMessageEndEvent(
                                        type=EventType.TEXT_MESSAGE_END,
                                        message_id=current_message_id,
                                        timestamp=int(time.time() * 1000),
                                    )
                                )
                                message_started = False
                        turn_saw_tool_call_chunks = True
                        pending_turn_text = ""
                        turn_plain_text_chunks = 0
                        turn_text_live = False
                        live_turn_emitted_text = ""
                    for ev in tool_chunk_events:
                        yield ev

                    # thinking 仍即时推送；正文默认进缓冲，确认无工具后再实时推。
                    content_events, _, _, thinking_started, text_piece = self._handle_chat_model_stream_content(
                        chunk,
                        encoder,
                        run_id,
                        pending_turn_strip_key,
                        False,
                        show_think,
                        thinking_started,
                        text_strip_buffers,
                        emit_text=False,
                    )
                    for ev in content_events:
                        yield ev

                    if turn_saw_tool_call_chunks:
                        # 本轮已确定走工具：丢弃旁白，不再累积/推送正文。
                        pending_turn_text = ""
                    elif text_piece:
                        pending_turn_text += text_piece
                        turn_plain_text_chunks += 1
                        # show_think=False：禁止提前开播，等 chat_model_end 再裁定（防长旁白泄漏）。
                        should_go_live = show_think and (
                            turn_text_live
                            or turn_plain_text_chunks >= _AGUI_PLAIN_TEXT_LIVE_AFTER_CHUNKS
                            or len(pending_turn_text) >= _AGUI_PLAIN_TEXT_LIVE_AFTER_CHARS
                        )
                        if should_go_live and pending_turn_text:
                            live_events, current_message_id, message_started = self._emit_live_text_delta(
                                encoder,
                                run_id,
                                pending_turn_text,
                                message_id=current_message_id,
                                message_started=message_started,
                            )
                            for ev in live_events:
                                yield ev
                            if _record_emitted_text_signatures(live_events, emitted_text_signatures):
                                emitted_any_text_this_run = True
                            live_turn_emitted_text += pending_turn_text
                            pending_turn_text = ""
                            turn_text_live = True

                elif event_type == "on_tool_start":
                    for ev in self._handle_tool_start_event(
                        event,
                        event_data,
                        encoder,
                        current_message_id,
                        current_tool_calls,
                    ):
                        yield ev

                elif event_type == "on_tool_end":
                    for ev in self._handle_tool_end_event(event, event_data, encoder, current_tool_calls):
                        yield ev
                    tool_result_seen_since_model_end = True

                elif event_type == "on_chat_model_end":
                    if token_usage_accumulator is not None and not token_usage_accumulator.middleware_tracking:
                        added, reported = token_usage_accumulator.add(event.get("run_id"), event_data.get("output"))
                        if added and not reported:
                            logger.warning(
                                "AGUI LLM call did not report token usage: run_id=%s",
                                event.get("run_id"),
                            )
                    leftover_strip = text_strip_buffers.pop(pending_turn_strip_key, "")
                    if leftover_strip:
                        pending_turn_text += strip_phantom_tool_calls(leftover_strip)

                    output = event_data.get("output")
                    end_tool_calls = getattr(output, "tool_calls", None) or []
                    turn_has_tools = bool(end_tool_calls) or turn_saw_tool_call_chunks
                    # 有工具：丢弃本轮旁白缓冲，只补工具事件。
                    # 已实时推送：冲掉剩余缓冲并结束消息，禁止再整段重发。
                    # 未实时推送的短纯文本：chat_model_end 一次性发出。
                    if turn_has_tools:
                        pending_turn_text = ""
                        fallback_text = ""
                        allow_non_streaming_text = bool(tool_result_seen_since_model_end)
                        if live_turn_emitted_text and current_message_id:
                            yield encoder.encode(
                                CustomEvent(
                                    type=EventType.CUSTOM,
                                    name="assistant_text_retract",
                                    value={"message_id": current_message_id, "reason": "tool_call"},
                                )
                            )
                        if message_started and current_message_id is not None:
                            yield encoder.encode(
                                TextMessageEndEvent(
                                    type=EventType.TEXT_MESSAGE_END,
                                    message_id=current_message_id,
                                    timestamp=int(time.time() * 1000),
                                )
                            )
                            message_started = False
                        live_turn_emitted_text = ""
                        turn_text_live = False
                    elif turn_text_live:
                        if pending_turn_text:
                            live_events, current_message_id, message_started = self._emit_live_text_delta(
                                encoder,
                                run_id,
                                pending_turn_text,
                                message_id=current_message_id,
                                message_started=message_started,
                            )
                            for ev in live_events:
                                yield ev
                            if _record_emitted_text_signatures(live_events, emitted_text_signatures):
                                emitted_any_text_this_run = True
                            live_turn_emitted_text += pending_turn_text
                            pending_turn_text = ""
                        if live_turn_emitted_text:
                            emitted_text_signatures.add(live_turn_emitted_text)
                            emitted_any_text_this_run = True
                        if message_started and current_message_id is not None:
                            yield encoder.encode(
                                TextMessageEndEvent(
                                    type=EventType.TEXT_MESSAGE_END,
                                    message_id=current_message_id,
                                    timestamp=int(time.time() * 1000),
                                )
                            )
                            message_started = False
                        fallback_text = ""
                        allow_non_streaming_text = False
                    else:
                        fallback_text = pending_turn_text
                        allow_non_streaming_text = True

                    model_metadata = dict(getattr(output, "response_metadata", {}) or {})
                    model_reason = str(model_metadata.get("finish_reason") or model_metadata.get("stop_reason") or "").casefold()
                    token_usage = model_metadata.get("token_usage") or {}
                    completion_tokens = token_usage.get("completion_tokens") or token_usage.get("output_tokens") or 0
                    if model_reason in {"length", "max_tokens", "max_output_tokens", "token_limit"} or (
                        request.max_output_tokens > 0 and isinstance(completion_tokens, int) and completion_tokens >= request.max_output_tokens
                    ):
                        output_truncated = True
                    chat_model_end_events = self._handle_chat_model_end_event(
                        event_data,
                        encoder,
                        current_message_id,
                        current_tool_calls,
                        # 已实时推送过正文时传 True，避免 end 再用 output.content 整段重发。
                        message_started=turn_text_live,
                        allow_non_streaming_text=allow_non_streaming_text,
                        fallback_text=fallback_text,
                        emitted_text_signatures=emitted_text_signatures,
                    )
                    # 收集本轮 chat_model_end 实际 emit 的文本指纹(含拆段后的全文),
                    # 后续 on_chain_end 若再 emit 相同内容会基于此集合去重。
                    if _record_emitted_text_signatures(chat_model_end_events, emitted_text_signatures):
                        emitted_any_text_this_run = True
                    for ev in chat_model_end_events:
                        yield ev
                    pending_turn_text = ""
                    turn_saw_tool_call_chunks = False
                    turn_plain_text_chunks = 0
                    turn_text_live = False
                    live_turn_emitted_text = ""
                    message_started = False
                    tool_result_seen_since_model_end = False

                elif event_type == "on_chain_end":
                    # add_chat_history_node 结束时 last=上一轮助手，不得当成本轮直答。
                    # 仍回填 ToolMessage（若有），但不 emit 文本。
                    if str(event.get("name") or "") == "add_chat_history_node":
                        chain_events = self._handle_chain_end_tool_results_only(
                            event_data,
                            encoder,
                            current_tool_calls,
                        )
                    else:
                        # DeepAgent 父/子图会多次触发 on_chain_end,output.messages 都带同一份
                        # 最终 AI 文本。先用已发过的文本指纹去重,避免重复 emit 整段回答。
                        chain_events = self._handle_chain_end_messages_dedup(
                            event_data,
                            encoder,
                            current_tool_calls,
                            emitted_text_signatures,
                        )
                    # 把本次 chain_end emit 的文本也加入指纹(含拆段全文),防止后续 chain_end 再发一遍
                    if _record_emitted_text_signatures(chain_events, emitted_text_signatures):
                        emitted_any_text_this_run = True
                    for ev in chain_events:
                        yield ev

                elif event_type == "on_custom_event":
                    # 转发自定义事件（如 agent_step_progress）
                    custom_name = event.get("name", "")
                    if custom_name:
                        yield encoder.encode(
                            CustomEvent(
                                type=EventType.CUSTOM,
                                name=custom_name,
                                value=event_data,
                            )
                        )

            # 清空剩余的浏览器事件
            try:
                while True:
                    browser_event = browser_event_queue.get_nowait()
                    yield browser_event
            except asyncio.QueueEmpty:
                pass

            if output_truncated and (request.extra_config or {}).get("wiki_budget") is not None:
                warning_message_id = current_message_id or str(uuid.uuid4())
                if not message_started:
                    yield encoder.encode(
                        TextMessageStartEvent(
                            type=EventType.TEXT_MESSAGE_START,
                            message_id=warning_message_id,
                            timestamp=int(time.time() * 1000),
                        )
                    )
                yield encoder.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=warning_message_id,
                        delta="\n\n> 回答已达到输出 token 上限，内容可能被截断",
                        timestamp=int(time.time() * 1000),
                    )
                )
                if not message_started:
                    yield encoder.encode(
                        TextMessageEndEvent(
                            type=EventType.TEXT_MESSAGE_END,
                            message_id=warning_message_id,
                            timestamp=int(time.time() * 1000),
                        )
                    )
            # 发送消息结束事件
            if message_started and current_message_id is not None:
                yield encoder.encode(
                    TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=current_message_id,
                        timestamp=int(time.time() * 1000),
                    )
                )

            if thinking_started:
                yield encoder.encode(
                    ThinkingTextMessageEndEvent(
                        type=EventType.THINKING_TEXT_MESSAGE_END,
                        timestamp=int(time.time() * 1000),
                    )
                )

            if not emitted_any_text_this_run and not message_started:
                llm_calls = int(getattr(token_usage_accumulator, "call_count", 0) or 0) if token_usage_accumulator else 0
                logger.warning(
                    format_llm_empty_response_log(
                        stage="agui_stream",
                        endpoint=summarize_llm_endpoint(request),
                        extra=f"llm_calls={llm_calls} run_id={run_id}",
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
            classification = classify_llm_error(e)
            logger.exception(
                format_llm_failure_log(
                    stage="agui_stream",
                    classification=classification,
                    endpoint=summarize_llm_endpoint(request),
                )
            )
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message=f"{classification['user_message']}: {classification['detail']}"[:1000],
                    code=str(classification["code"]),
                    timestamp=int(time.time() * 1000),
                )
            )
        finally:
            stop_event.set()

    async def _handle_tool_calls(
        self,
        tool_calls: List[Any],
        encoder: EventEncoder,
        parent_message_id: str,
        current_tool_calls: Dict[str, Dict],
    ) -> AsyncGenerator[str, None]:
        """处理工具调用事件（异步生成器版本，用于流式场景）"""
        for tool_call in tool_calls:
            # 支持 dict 和 ToolCall 对象
            if hasattr(tool_call, "get"):
                tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id", f"tool_{uuid.uuid4()}")
                tool_name = tool_call.get("name", "unknown")
                tool_args = tool_call.get("args")
            else:
                tool_call_id = getattr(tool_call, "id", None) or f"tool_{uuid.uuid4()}"
                tool_name = getattr(tool_call, "name", "unknown")
                tool_args = getattr(tool_call, "args", None)

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
                if tool_args:
                    # Mask sensitive data (password, token, etc.) for SSE output only
                    masked_args = _mask_sensitive_data(tool_args) if isinstance(tool_args, dict) else tool_args
                    yield encoder.encode(
                        ToolCallArgsEvent(
                            type=EventType.TOOL_CALL_ARGS,
                            tool_call_id=tool_call_id,
                            delta=json.dumps(masked_args, ensure_ascii=False) if isinstance(masked_args, dict) else str(masked_args),
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
            # 创建 browser_steps 收集器（纯字符串列表）
            browser_steps_collector: List[str] = []
            last_evaluation: str = ""

            def sync_step_callback(step_info: Dict[str, Any]) -> None:
                """同步回调，收集 browser_use 步骤信息并格式化为字符串"""
                nonlocal last_evaluation
                step_number = step_info.get("step_number", 0)
                next_goal = step_info.get("next_goal", "")
                evaluation = step_info.get("evaluation", "")

                # 记录步骤: "step{n} {next_goal}"
                if next_goal:
                    browser_steps_collector.append(f"step{step_number} {next_goal}")

                # 保存最新的 evaluation 用于最终结果
                if evaluation:
                    last_evaluation = evaluation

            graph = await self.compile_graph(request)
            token_usage_accumulator = TokenUsageAccumulator()
            result = await self.invoke(
                graph,
                request,
                extra_configurable={
                    "browser_step_callback": sync_step_callback,
                    "token_usage_accumulator": token_usage_accumulator,
                },
            )

            # 添加最终结果
            if last_evaluation:
                browser_steps_collector.append(f"最终结果: {last_evaluation}")

            if token_usage_accumulator.call_count == 0:
                for message in result["messages"]:
                    if isinstance(message, AIMessage):
                        token_usage_accumulator.add(
                            getattr(message, "id", None),
                            message,
                        )

            if token_usage_accumulator.missing_usage_calls:
                logger.warning(
                    "Synchronous Agent LLM calls did not report token usage: missing_usage_calls=%s",
                    token_usage_accumulator.missing_usage_calls,
                )
            usage = token_usage_accumulator.as_openai_usage()
            last_message = result["messages"][-1] if result["messages"] else None
            last_message_content = last_message.content if last_message is not None else ""
            metadata = dict(last_message.response_metadata or {}) if isinstance(last_message, AIMessage) else {}
            finish_reason = str(metadata.get("finish_reason") or metadata.get("stop_reason") or "").strip() or None
            output_truncated = str(finish_reason or "").casefold() in {"length", "max_tokens", "max_output_tokens", "token_limit"} or (
                request.max_output_tokens > 0 and usage["completion_tokens"] >= request.max_output_tokens
            )
            return BasicLLMResponse(
                message=last_message_content,
                total_tokens=usage["total_tokens"],
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                llm_call_count=token_usage_accumulator.call_count,
                token_usage_calls=token_usage_accumulator.as_call_details(),
                finish_reason=finish_reason,
                output_truncated=output_truncated,
                browser_steps=browser_steps_collector,
            )
        except Exception as e:
            # 处理常规异常，包括 TaskGroup 异常；
            # CancelledError / KeyboardInterrupt 不在此捕获，保持向上传播。
            error_msg = str(e)

            # 提取 TaskGroup 中的实际错误信息
            if "unhandled errors in a TaskGroup" in error_msg:
                if hasattr(e, "__cause__") and e.__cause__:
                    error_msg = f"TaskGroup error: {str(e.__cause__)}"
                elif hasattr(e, "exceptions"):
                    # ExceptionGroup 有 exceptions 属性
                    sub_errors = [str(ex) for ex in e.exceptions]
                    error_msg = f"TaskGroup errors: {', '.join(sub_errors)}"

            logger.exception(f"Graph execute 执行失败: {error_msg}")

            # 重新抛出异常，让上层处理
            raise RuntimeError(f"Agent execution failed: {error_msg}") from e
