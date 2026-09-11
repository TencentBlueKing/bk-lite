import asyncio

import pytest

from apps.opspilot.metis.llm.chain import graph as graph_module
from apps.opspilot.metis.llm.chain.graph import _merge_async_streams

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_慢消费时输出队列保持容量边界和事件顺序(monkeypatch):
    original_queue = asyncio.Queue
    output_queues = []

    class _TrackingQueue(original_queue):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.peak_size = 0
            output_queues.append(self)

        async def put(self, item):
            await super().put(item)
            self.peak_size = max(self.peak_size, self.qsize())

    browser_queue = original_queue()
    monkeypatch.setattr(graph_module.asyncio, "Queue", _TrackingQueue)
    produced = 0

    async def langgraph_stream():
        nonlocal produced
        for index in range(300):
            produced += 1
            yield index

    merged = _merge_async_streams(langgraph_stream(), browser_queue, asyncio.Event())
    first = await anext(merged)
    await asyncio.sleep(0.05)

    capacity = getattr(graph_module, "SSE_OUTPUT_QUEUE_MAXSIZE", None)
    output_queue = output_queues[0]
    assert capacity == 100
    assert output_queue.maxsize == capacity
    assert output_queue.peak_size <= capacity
    assert produced <= capacity + 2

    remaining = [item async for item in merged]
    assert [first, *remaining] == [("langgraph", index) for index in range(300)]


@pytest.mark.asyncio
async def test_满队列时下游关闭仍会完成生产者清理():
    capacity_reached = asyncio.Event()
    finalized = asyncio.Event()

    async def langgraph_stream():
        try:
            for index in range(graph_module.SSE_OUTPUT_QUEUE_MAXSIZE + 10):
                if index == graph_module.SSE_OUTPUT_QUEUE_MAXSIZE + 1:
                    capacity_reached.set()
                yield index
        finally:
            finalized.set()

    merged = _merge_async_streams(langgraph_stream(), asyncio.Queue(), asyncio.Event())
    assert await anext(merged) == ("langgraph", 0)
    await asyncio.wait_for(capacity_reached.wait(), timeout=1)

    await asyncio.wait_for(merged.aclose(), timeout=1)
    await asyncio.wait_for(finalized.wait(), timeout=1)
