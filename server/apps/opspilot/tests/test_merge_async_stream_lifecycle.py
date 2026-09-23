import asyncio

import pytest

from apps.opspilot.metis.llm.chain import graph as graph_module
from apps.opspilot.metis.llm.chain.graph import _merge_async_streams

pytestmark = pytest.mark.unit


class _ObservableEventQueue(asyncio.Queue):
    def __init__(self, stop_event):
        super().__init__()
        self.stop_event = stop_event
        self.cleanup_cancelled = asyncio.Event()

    async def get(self):
        try:
            return await super().get()
        except asyncio.CancelledError:
            if self.stop_event.is_set():
                self.cleanup_cancelled.set()
            raise


@pytest.mark.asyncio
async def test_下游关闭会取消阻塞中的LangGraph任务():
    release = asyncio.Event()
    finalized = asyncio.Event()
    stop_event = asyncio.Event()
    event_queue = _ObservableEventQueue(stop_event)

    async def langgraph_stream():
        try:
            yield "first"
            await release.wait()
        finally:
            finalized.set()

    merged = _merge_async_streams(langgraph_stream(), event_queue, stop_event)
    assert await anext(merged) == ("langgraph", "first")

    try:
        await asyncio.wait_for(merged.aclose(), timeout=1)
    finally:
        release.set()

    await asyncio.wait_for(finalized.wait(), timeout=1)
    await asyncio.wait_for(event_queue.cleanup_cancelled.wait(), timeout=1)
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_外部取消会收口所有子任务():
    release = asyncio.Event()
    finalized = asyncio.Event()
    started = asyncio.Event()
    stop_event = asyncio.Event()
    event_queue = _ObservableEventQueue(stop_event)

    async def langgraph_stream():
        try:
            started.set()
            yield "first"
            await release.wait()
        finally:
            finalized.set()

    async def consume():
        return [item async for item in _merge_async_streams(langgraph_stream(), event_queue, stop_event)]

    consumer = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=0.2)
    consumer.cancel()

    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(consumer), timeout=1)
    finally:
        release.set()
        if not consumer.done():
            try:
                await asyncio.wait_for(consumer, timeout=0.2)
            except asyncio.CancelledError:
                pass

    assert finalized.is_set()
    await asyncio.wait_for(event_queue.cleanup_cancelled.wait(), timeout=1)
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_LangGraph自然完成保持事件顺序():
    async def langgraph_stream():
        yield "first"
        yield "second"

    stop_event = asyncio.Event()
    items = [item async for item in _merge_async_streams(langgraph_stream(), asyncio.Queue(), stop_event)]

    assert items == [("langgraph", "first"), ("langgraph", "second")]
    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_LangGraph原始异常继续向调用方传播():
    original_error = RuntimeError("upstream failed")

    async def langgraph_stream():
        yield "first"
        raise original_error

    merged = _merge_async_streams(langgraph_stream(), asyncio.Queue(), asyncio.Event())

    assert await anext(merged) == ("langgraph", "first")
    with pytest.raises(RuntimeError) as exc_info:
        await anext(merged)

    assert exc_info.value is original_error


@pytest.mark.asyncio
async def test_LangGraph主动取消继续向调用方传播():
    original_error = asyncio.CancelledError("upstream cancelled")

    async def langgraph_stream():
        yield "first"
        raise original_error

    merged = _merge_async_streams(langgraph_stream(), asyncio.Queue(), asyncio.Event())

    assert await anext(merged) == ("langgraph", "first")
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await anext(merged)

    assert isinstance(exc_info.value, asyncio.CancelledError)


@pytest.mark.asyncio
async def test_等待上游期间保持发送keepalive(monkeypatch):
    release = asyncio.Event()

    async def langgraph_stream():
        await release.wait()
        if False:
            yield None

    monkeypatch.setattr(graph_module, "SSE_KEEPALIVE_INTERVAL_SECONDS", 0.01)
    merged = _merge_async_streams(langgraph_stream(), asyncio.Queue(), asyncio.Event())

    assert await asyncio.wait_for(anext(merged), timeout=1) == ("keepalive", "waiting_model")
    await asyncio.wait_for(merged.aclose(), timeout=1)


@pytest.mark.asyncio
async def test_源生成器忙于吞掉事件时仍发送sse保活(monkeypatch):
    from ag_ui.encoder import EventEncoder

    from apps.opspilot.metis.llm.chain.graph import iter_sse_frames_with_idle_keepalive

    monkeypatch.setattr(graph_module, "SSE_KEEPALIVE_INTERVAL_SECONDS", 0.02)

    async def silent_busy_stream():
        await asyncio.sleep(0.08)
        yield 'data: {"type":"RUN_FINISHED"}\n\n'

    frames = [frame async for frame in iter_sse_frames_with_idle_keepalive(silent_busy_stream(), EventEncoder())]
    assert any(frame.startswith(": keepalive") for frame in frames)
    assert any("stream_keepalive" in frame for frame in frames)
    assert any("RUN_FINISHED" in frame for frame in frames)


@pytest.mark.asyncio
async def test_hung_langgraph_stream_still_delivers_node_finished():
    from apps.opspilot.metis.llm.chain.nested_stream import NODE_FINISHED_EVENT

    started = asyncio.Event()

    async def langgraph_stream():
        started.set()
        await asyncio.Event().wait()
        yield "late"

    owned = asyncio.Queue()
    await owned.put({"event": "on_tool_end", "data": {"output": "ok"}})
    await owned.put({"event": NODE_FINISHED_EVENT})
    merged = _merge_async_streams(langgraph_stream(), asyncio.Queue(), asyncio.Event(), owned)

    kinds = []

    async def collect():
        async for kind, _data in merged:
            kinds.append(kind)
            if kind == "node_finished":
                return

    await asyncio.wait_for(collect(), timeout=2)
    await merged.aclose()
    assert started.is_set()
    assert "owned" in kinds
    assert kinds[-1] == "node_finished"
