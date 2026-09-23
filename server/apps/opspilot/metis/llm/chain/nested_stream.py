"""把 DeepAgent 的 token / 工具事件写进本请求自己的队列。

父级 ``_AstreamEventsCallbackHandler`` 会 tap 子级 LLM 的 HTTP 流，节点返回后
SSE 仍要等它收尾。这里的桥只往 ``agui_owned_event_queue`` 放事件，不调用父级
``_send``。回答是否完成由节点返回时写入的 ``opspilot_node_finished`` 决定。
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, GenerationChunk
from langchain_core.runnables.config import var_child_runnable_config

OWNED_EVENT_QUEUE_KEY = "agui_owned_event_queue"
NODE_FINISHED_EVENT = "opspilot_node_finished"
PLANNED_TOOL_STEPS_KEY = "planned_tool_steps"
PLANNED_STEP_HOLDER_KEY = "planned_step_holder"

# 本轮 SSE / 节点共用的引用（同一 dict 对象，不用 ContextVar：
# agui 消费端与工具回调常在别的 Task/线程，ContextVar 读不到）。
_active_planned_tool_steps: dict[str, int] | None = None
_active_step_holder: dict[str, Any] | None = None
_active_owned_queue: asyncio.Queue | None = None


def bind_owned_event_queue(queue: asyncio.Queue | None) -> asyncio.Queue | None:
    """工具回调拿到的 config 经常没有本轮队列，选择事件回退到这里。"""
    global _active_owned_queue
    previous = _active_owned_queue
    _active_owned_queue = queue
    return previous


def owned_event_queue(config: dict | None) -> asyncio.Queue | None:
    configurable = (config or {}).get("configurable") or {}
    queue = configurable.get(OWNED_EVENT_QUEUE_KEY)
    if isinstance(queue, asyncio.Queue):
        return queue
    return None


class OwnedEventBridge(AsyncCallbackHandler):
    """子调用的 token / 工具回调只进本请求队列，不是父级 streaming tap。"""

    def __init__(self, queue: asyncio.Queue, step_holder: dict | None = None) -> None:
        super().__init__()
        self._queue = queue
        self._step_holder = step_holder if isinstance(step_holder, dict) else {}

    def _current_step_index(self) -> int | None:
        # 工具回调常在线程池或 ainvoke 返回之后，读共享 holder，不读 ContextVar。
        for source in (self._step_holder, _active_step_holder):
            if not isinstance(source, dict):
                continue
            held = source.get("step_index")
            if isinstance(held, int) and not isinstance(held, bool) and held >= 1:
                return held
        return None

    def _send(self, event: dict) -> None:
        step_index = self._current_step_index()
        if step_index is not None:
            metadata = dict(event.get("metadata") or {})
            metadata["opspilot_step_index"] = step_index
            event = {**event, "metadata": metadata}
        event = {**event, "_enqueued_at": time.monotonic()}
        try:
            self._queue.put_nowait(event)
        except Exception:
            return

    async def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: GenerationChunk | ChatGenerationChunk | None = None,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        message = getattr(chunk, "message", None) if chunk is not None else None
        if message is None:
            message = AIMessageChunk(content=token if isinstance(token, str) else "")
        tool_chunks = getattr(message, "tool_call_chunks", None) or []
        if tool_chunks and not str(getattr(message, "content", "") or "").strip():
            return
        self._send(
            {
                "event": "on_chat_model_stream",
                "data": {"chunk": message},
                "run_id": str(run_id),
                "name": "ChatOpenAI",
                "tags": [],
                "metadata": {},
                "parent_ids": [],
            }
        )

    async def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        message = None
        generations = getattr(response, "generations", None) or []
        if generations and generations[0]:
            message = getattr(generations[0][0], "message", None)
        if message is None or getattr(message, "tool_calls", None):
            return
        self._send(
            {
                "event": "on_chat_model_end",
                "data": {"output": message},
                "run_id": str(run_id),
                "name": "ChatOpenAI",
                "tags": [],
                "metadata": {},
                "parent_ids": [],
            }
        )

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        name: str | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = name or serialized.get("name") or "unknown"
        self._send(
            {
                "event": "on_tool_start",
                "data": {"input": inputs or {}},
                "name": tool_name,
                "tags": [],
                "run_id": str(run_id),
                "metadata": {},
                "parent_ids": [],
            }
        )

    async def on_custom_event(
        self,
        name: str,
        data: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        publish_owned_custom_event(self._queue, name, data)

    async def on_tool_end(self, output: Any, *, run_id: UUID, name: str | None = None, **kwargs: Any) -> None:
        self._send(
            {
                "event": "on_tool_end",
                "data": {"output": output},
                "run_id": str(run_id),
                "name": name or "unknown",
                "tags": [],
                "metadata": {},
                "parent_ids": [],
            }
        )


def planned_step_holder(config: dict | None) -> dict:
    global _active_step_holder
    configurable = (config or {}).get("configurable")
    if not isinstance(configurable, dict):
        holder = {"step_index": None}
        _active_step_holder = holder
        return holder
    holder = configurable.get(PLANNED_STEP_HOLDER_KEY)
    if not isinstance(holder, dict):
        holder = {"step_index": None}
        configurable[PLANNED_STEP_HOLDER_KEY] = holder
    _active_step_holder = holder
    return holder


def nested_agent_callbacks(config: dict | None) -> list:
    """子 Agent 只用自有队列桥，不挂父级 astream_events handler。"""
    queue = owned_event_queue(config)
    if queue is None:
        return []
    bind_owned_event_queue(queue)
    return [OwnedEventBridge(queue, planned_step_holder(config))]


def publish_owned_custom_event(queue_or_config: Any, name: str, data: Any) -> bool:
    """把自定义事件写进本请求队列。计划步骤里父级 astream 回调已被摘掉。"""
    if isinstance(queue_or_config, asyncio.Queue):
        queue = queue_or_config
    else:
        queue = owned_event_queue(queue_or_config if isinstance(queue_or_config, dict) else None)
        if queue is None and isinstance(_active_owned_queue, asyncio.Queue):
            queue = _active_owned_queue
    if queue is None or not name:
        return False
    try:
        queue.put_nowait(
            {
                "event": "on_custom_event",
                "name": name,
                "data": data,
                "tags": [],
                "metadata": {},
                "parent_ids": [],
                "_enqueued_at": time.monotonic(),
            }
        )
    except Exception:
        return False
    return True


def publish_node_finished(config: dict | None) -> None:
    """节点返回即视为本轮回答完成，不依赖 astream_events 收尾。"""
    queue = owned_event_queue(config)
    if queue is None:
        return
    try:
        queue.put_nowait({"event": NODE_FINISHED_EVENT, "_enqueued_at": time.monotonic()})
    except Exception:
        return


@contextmanager
def isolated_child_callback_context() -> Iterator[None]:
    """调用子 Agent 期间，不要让父级 astream_events handler 被 merge 回 callbacks。

    ``merge_configs`` 会把上下文里的 callbacks 和本次传入的列表拼在一起。
    只把本次 callbacks 换成桥，父 handler 仍在，模型 HTTP 流继续被父级 tap，
    节点返回后 SSE 还会空转，同一次工具也会出现两张卡。
    """
    current = var_child_runnable_config.get()
    if not current or not current.get("callbacks"):
        yield
        return
    stripped = dict(current)
    stripped["callbacks"] = []
    token = var_child_runnable_config.set(stripped)
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


@contextmanager
def bind_planned_step_index(step_index: int, config: dict | None = None) -> Iterator[None]:
    """本步执行期间把步骤号写进共享 holder。

    工具回调常晚于 ainvoke 返回，退出时不清空；下一步 bind 会覆盖，planned_run
    结束时由 clear_planned_step_holder 收口。
    """
    holder = planned_step_holder(config) if isinstance(config, dict) else None
    if isinstance(holder, dict):
        holder["step_index"] = step_index
    yield


def clear_planned_step_holder(config: dict | None = None) -> None:
    holder = planned_step_holder(config) if isinstance(config, dict) else _active_step_holder
    if isinstance(holder, dict):
        holder["step_index"] = None


def activate_planned_tool_steps(bindings: dict[str, int]) -> dict[str, int] | None:
    """本轮 SSE 与节点共用同一张 tool_call_id → step_index 表。"""
    global _active_planned_tool_steps
    previous = _active_planned_tool_steps
    _active_planned_tool_steps = bindings
    return previous


def reset_planned_tool_steps(previous: dict[str, int] | None) -> None:
    global _active_planned_tool_steps, _active_step_holder
    _active_planned_tool_steps = previous
    _active_step_holder = None


def lookup_planned_tool_step(tool_call_id: str) -> int | None:
    bindings = _active_planned_tool_steps
    if not isinstance(bindings, dict) or not tool_call_id:
        return None
    step_index = bindings.get(tool_call_id)
    if isinstance(step_index, int) and not isinstance(step_index, bool) and step_index >= 1:
        return step_index
    return None


def current_planned_step_index() -> int | None:
    holder = _active_step_holder
    if not isinstance(holder, dict):
        return None
    held = holder.get("step_index")
    if isinstance(held, int) and not isinstance(held, bool) and held >= 1:
        return held
    return None


def remember_planned_tool_steps(config: dict | None, step_index: int, messages: list) -> None:
    """把本步实际产生的 tool_call_id 记到共享表，供 chain_end 补发时归位。"""
    global _active_planned_tool_steps
    if not isinstance(step_index, int) or step_index < 1:
        return
    configurable = (config or {}).get("configurable") or {}
    bindings = configurable.get(PLANNED_TOOL_STEPS_KEY)
    if not isinstance(bindings, dict):
        bindings = _active_planned_tool_steps
    if not isinstance(bindings, dict):
        return
    _active_planned_tool_steps = bindings
    for message in messages or []:
        if isinstance(message, ToolMessage):
            tool_call_id = str(getattr(message, "tool_call_id", "") or "").strip()
            if tool_call_id:
                bindings[tool_call_id] = step_index
            continue
        for tool_call in getattr(message, "tool_calls", None) or []:
            if hasattr(tool_call, "get"):
                tool_call_id = str(tool_call.get("id") or "").strip()
            else:
                tool_call_id = str(getattr(tool_call, "id", "") or "").strip()
            if tool_call_id:
                bindings[tool_call_id] = step_index


def enable_nested_token_streaming(llm: Any) -> None:
    """让 DeepAgent 的模型走 token 流，这样桥能逐段转发，而不是整段一次返回。"""
    if not isinstance(llm, BaseChatModel):
        return
    cls = type(llm)
    overrides_stream = cls._stream is not BaseChatModel._stream or cls._astream is not BaseChatModel._astream
    if not overrides_stream:
        return
    if getattr(llm, "disable_streaming", None) is True:
        return
    if hasattr(llm, "streaming"):
        llm.streaming = True
