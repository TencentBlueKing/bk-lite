import asyncio
import uuid

import pytest

from apps.opspilot.metis.llm.chain.nested_stream import OwnedEventBridge

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def settings():
    class _Settings:
        MIDDLEWARE = []
        CACHES = {}

    return _Settings()


async def test_慢消费者会阻塞生产并在恢复后完整收到事件():
    queue = asyncio.Queue(maxsize=1)
    bridge = OwnedEventBridge(queue)
    run_id = uuid.UUID(int=1)
    await bridge.on_llm_new_token("first", run_id=run_id)
    producer = asyncio.create_task(bridge.on_llm_new_token("second", run_id=run_id))
    try:
        await asyncio.sleep(0)
        assert not producer.done()
        assert (await queue.get())["data"]["chunk"].content == "first"
        await asyncio.wait_for(producer, 1)
        assert (await queue.get())["data"]["chunk"].content == "second"
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)


async def test_选择事件满队列时等待而不丢失():
    queue = asyncio.Queue(maxsize=1)
    await queue.put({"name": "existing"})
    bridge = OwnedEventBridge(queue)
    task = asyncio.create_task(bridge.on_custom_event("user_choice_request", {"choice_id": "fixture"}, run_id=uuid.UUID(int=1)))
    try:
        await asyncio.sleep(0)
        assert not task.done()
        assert (await queue.get())["name"] == "existing"
        await asyncio.wait_for(task, 1)
        event = await queue.get()
        assert event["name"] == "user_choice_request"
        assert event["data"] == {"choice_id": "fixture"}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_真实流的子调用事件队列限制生产速度(monkeypatch):
    import gc

    from apps.opspilot.metis.llm.chain import graph as module
    from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
    from apps.opspilot.metis.llm.chain.nested_stream import OWNED_EVENT_QUEUE_KEY, nested_agent_callbacks

    async def no_interrupt(_execution_id):
        return False

    monkeypatch.setattr(module, "is_interrupt_requested_async", no_interrupt)
    queues = []
    produced = []
    released = asyncio.Event()
    baseline = set(asyncio.all_tasks())

    class Compiled:
        async def astream_events(self, *args, config, **kwargs):
            bridge = nested_agent_callbacks(config)[0]
            queues.append(config["configurable"][OWNED_EVENT_QUEUE_KEY])
            try:
                for index in range(3000):
                    await bridge.on_llm_new_token("x" * 128, run_id=uuid.UUID(int=1))
                    produced.append(index)
                await asyncio.sleep(30)
            finally:
                released.set()
            if False:
                yield None

    class Graph(module.BasicGraph):
        async def compile_graph(self, request):
            return Compiled()

    stream = Graph().agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))
    try:
        async with asyncio.timeout(1):
            async for frame in stream:
                if "TEXT_MESSAGE_CONTENT" in frame:
                    break
        await asyncio.sleep(0.05)
        assert len(produced) < 3000
        assert 0 < queues[0].qsize() <= 100
    finally:
        await stream.aclose()
        # 独立编译流关闭回归由 #5411 处理；这里等待生成器终结调度。
        gc.collect()
        await asyncio.sleep(0.05)
        remaining = [task for task in asyncio.all_tasks() - baseline if not task.done()]
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
    assert released.is_set()


@pytest.mark.parametrize("event_kind", ["token", "tool_start", "tool_end", "custom", "choice", "finished"])
@pytest.mark.parametrize("termination", ["cancel", "timeout"])
async def test_满队列发布可取消超时并能再次调用(event_kind, termination):
    from apps.opspilot.metis.llm.chain.nested_stream import OWNED_EVENT_QUEUE_KEY, publish_node_finished, publish_owned_custom_event

    queue = asyncio.Queue(maxsize=1)
    await queue.put({"event": "existing"})
    bridge = OwnedEventBridge(queue)
    run_id = uuid.UUID(int=1)
    config = {"configurable": {OWNED_EVENT_QUEUE_KEY: queue}}

    async def publish():
        if event_kind == "token":
            await bridge.on_llm_new_token("fixture", run_id=run_id)
        elif event_kind == "tool_start":
            await bridge.on_tool_start({"name": "fixture"}, "", run_id=run_id)
        elif event_kind == "tool_end":
            await bridge.on_tool_end("fixture", run_id=run_id)
        elif event_kind == "custom":
            await bridge.on_custom_event("fixture", {}, run_id=run_id)
        elif event_kind == "choice":
            assert await publish_owned_custom_event(config, "user_choice_result", {"selected": ["fixture"]})
        else:
            await publish_node_finished(config)

    task = asyncio.create_task(publish())
    try:
        await asyncio.sleep(0)
        assert not task.done()
        if termination == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(task, 0.01)
        assert queue.qsize() == 1
        assert (await queue.get())["event"] == "existing"
        await asyncio.wait_for(publish(), 1)
        assert queue.qsize() == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_选择工具等待队列容量并按序返回请求和结果(monkeypatch):
    from apps.opspilot.metis.llm.chain import approval_tools
    from apps.opspilot.metis.llm.chain.nested_stream import OWNED_EVENT_QUEUE_KEY

    async def user_response(**kwargs):
        return {"selected": ["option-a"], "source": "user"}

    monkeypatch.setattr(approval_tools, "wait_for_choice", user_response)
    queue = asyncio.Queue(maxsize=1)
    await queue.put({"name": "existing"})
    tool = approval_tools.ApprovalToolsMixin()._build_choice_tool()
    task = asyncio.create_task(
        tool.ainvoke(
            {"question": "选择目标", "question_type": "single_select", "options": ["option-a", "option-b"]},
            config={"configurable": {OWNED_EVENT_QUEUE_KEY: queue, "execution_id": "fixture"}},
        )
    )
    try:
        await asyncio.sleep(0.01)
        assert not task.done()
        assert (await queue.get())["name"] == "existing"
        request = await asyncio.wait_for(queue.get(), 1)
        result = await asyncio.wait_for(queue.get(), 1)
        answer = await asyncio.wait_for(task, 1)
        assert request["name"] == "user_choice_request"
        assert result["name"] == "user_choice_result"
        assert request["data"]["choice_id"] == result["data"]["choice_id"]
        assert result["data"]["selected"] == ["option-a"]
        assert "用户回答: option-a" in answer
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_关闭真实流会回收受保护的模型结束回调(monkeypatch):
    import gc

    from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from apps.opspilot.metis.llm.chain import graph as module
    from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
    from apps.opspilot.metis.llm.chain.nested_stream import nested_agent_callbacks

    async def no_interrupt(_execution_id):
        return False

    monkeypatch.setattr(module, "is_interrupt_requested_async", no_interrupt)
    baseline = set(asyncio.all_tasks())

    class Compiled:
        async def astream_events(self, *args, config, **kwargs):
            manager = AsyncCallbackManagerForLLMRun(
                run_id=uuid.UUID(int=1), handlers=nested_agent_callbacks(config), inheritable_handlers=[]
            )
            for _ in range(500):
                await manager.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="fixture response"))]]))
            if False:
                yield None

    class Graph(module.BasicGraph):
        async def compile_graph(self, request):
            return Compiled()

    stream = Graph().agui_stream(BasicLLMRequest(thread_id="fixture", extra_config={}))
    try:
        async with asyncio.timeout(1):
            async for frame in stream:
                if "TEXT_MESSAGE_CONTENT" in frame:
                    break
        await asyncio.sleep(0.05)
        await stream.aclose()
        gc.collect()
        await asyncio.sleep(0.1)
        assert not [task for task in asyncio.all_tasks() - baseline if not task.done()]
    finally:
        remaining = [task for task in asyncio.all_tasks() - baseline if not task.done()]
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        await stream.aclose()


async def test_请求队列关闭等待所有阻塞入队且重复关闭安全():
    from apps.opspilot.metis.llm.chain.nested_stream import OwnedEventQueue

    queue = OwnedEventQueue(maxsize=1)
    await queue.put("existing")
    producers = [asyncio.create_task(queue.put(index)) for index in range(3)]
    try:
        await asyncio.sleep(0)
        await queue.aclose()
        await queue.aclose()
        results = await asyncio.gather(*producers, return_exceptions=True)
        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert await queue.get() == "existing"
        with pytest.raises(asyncio.CancelledError):
            await queue.put("after-close")
    finally:
        for task in producers:
            task.cancel()
        await asyncio.gather(*producers, return_exceptions=True)
