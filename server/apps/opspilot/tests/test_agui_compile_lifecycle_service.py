import asyncio
import json

import pytest

from apps.opspilot.metis.llm.chain import graph as graph_module
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.chain.graph import BasicGraph

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def settings():
    class _Settings:
        MIDDLEWARE = []
        CACHES = {}

    return _Settings()


class _SlowCompileGraph(BasicGraph):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.finalized = asyncio.Event()

    async def compile_graph(self, request):
        try:
            self.started.set()
            await self.release.wait()
        finally:
            # 清理需要让出事件循环，验证关闭方确实等待了编译任务。
            await asyncio.sleep(0)
            self.finalized.set()


async def test_编译保活后关闭流会等待编译资源释放(monkeypatch):
    monkeypatch.setattr(graph_module, "SSE_KEEPALIVE_INTERVAL_SECONDS", 0.001)
    graph = _SlowCompileGraph()
    stream = graph.agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))
    try:
        async with asyncio.timeout(1):
            async for frame in stream:
                if "compile_graph" in frame:
                    break
        await asyncio.wait_for(stream.aclose(), timeout=1)
        assert graph.finalized.is_set()
        await stream.aclose()
    finally:
        graph.release.set()
        await asyncio.wait_for(graph.finalized.wait(), timeout=1)
        await stream.aclose()


@pytest.mark.parametrize("termination", ["cancel", "timeout"])
async def test_等待编译时取消或超时会等待资源释放(termination):
    graph = _SlowCompileGraph()
    stream = graph.agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))

    async def consume():
        return [frame async for frame in stream]

    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(graph.started.wait(), timeout=1)
        if termination == "cancel":
            consumer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(consumer, timeout=1)
        else:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(consumer, timeout=0.01)
        assert graph.finalized.is_set()
    finally:
        graph.release.set()
        if not consumer.done():
            consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await asyncio.wait_for(graph.finalized.wait(), timeout=1)
        await stream.aclose()


async def test_首帧后关闭不会启动编译任务():
    graph = _SlowCompileGraph()
    stream = graph.agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))
    await anext(stream)
    await stream.aclose()
    assert not graph.started.is_set()


class _EmptyCompiledGraph:
    async def astream_events(self, *args, **kwargs):
        if False:
            yield None


@pytest.mark.parametrize("outcome", ["complete", "failure", "cancel"])
async def test_编译终态保持原有事件与取消语义(outcome):
    original_error = asyncio.CancelledError("compile cancelled") if outcome == "cancel" else RuntimeError("compile fixture failed")
    finalized = asyncio.Event()

    class _FinishedCompileGraph(BasicGraph):
        async def compile_graph(self, request):
            try:
                if outcome != "complete":
                    raise original_error
                return _EmptyCompiledGraph()
            finally:
                finalized.set()

    stream = _FinishedCompileGraph().agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await anext(stream)
            async for _frame in stream:
                pass
        assert exc_info.value is original_error
    else:
        frames = [frame async for frame in stream]
        events = [json.loads(frame[6:]) for frame in frames if frame.startswith("data: ")]
        event_types = [event["type"] for event in events]
        assert event_types[0] == "RUN_STARTED"
        assert event_types[-1] == ("RUN_FINISHED" if outcome == "complete" else "RUN_ERROR")
        assert ("RUN_ERROR" in event_types) == (outcome == "failure")
    assert finalized.is_set()
    await stream.aclose()
