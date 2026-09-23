"""DeepAgent 子调用把事件写进本请求队列，不挂父级 astream_events handler。"""

import asyncio
import uuid

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk, LLMResult
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.runnables.config import merge_configs, var_child_runnable_config
from langchain_core.tracers._streaming import _StreamingCallbackHandler
from langchain_core.tracers.event_stream import _AstreamEventsCallbackHandler

from apps.opspilot.metis.llm.chain.nested_stream import (
    NODE_FINISHED_EVENT,
    OWNED_EVENT_QUEUE_KEY,
    PLANNED_STEP_HOLDER_KEY,
    OwnedEventBridge,
    attach_owned_stream_context,
    bind_planned_step_index,
    current_planned_step_index,
    isolated_child_callback_context,
    lookup_planned_tool_step,
    make_owned_stream_context,
    nested_agent_callbacks,
    publish_node_finished,
    publish_owned_custom_event,
    remember_planned_tool_steps,
)
from apps.opspilot.metis.llm.common.tool_failure import POLICY_RESULT_MARKER
from apps.opspilot.metis.llm.middleware.tool_runtime import repeated_successful_tool_denial


def _config_with_queue(queue, parent=None):
    callbacks = [parent] if parent is not None else []
    return {"callbacks": callbacks, "configurable": {OWNED_EVENT_QUEUE_KEY: queue}}


def test_nested_agent_callbacks_use_owned_queue_not_parent_handler():
    parent = _AstreamEventsCallbackHandler()
    queue = asyncio.Queue()
    callbacks = nested_agent_callbacks(_config_with_queue(queue, parent))

    assert parent not in callbacks
    assert len(callbacks) == 1
    bridge = callbacks[0]
    assert isinstance(bridge, OwnedEventBridge)
    assert not isinstance(bridge, _StreamingCallbackHandler)


def test_nested_agent_callbacks_empty_without_owned_queue():
    assert nested_agent_callbacks({"callbacks": []}) == []
    assert nested_agent_callbacks({}) == []


@pytest.mark.asyncio
async def test_owned_bridge_forwards_token_and_tool_to_queue():
    queue = asyncio.Queue()
    bridge = nested_agent_callbacks(_config_with_queue(queue))[0]
    run_id = uuid.uuid4()

    await bridge.on_llm_new_token(
        "你",
        chunk=ChatGenerationChunk(message=AIMessageChunk(content="你")),
        run_id=run_id,
    )
    await bridge.on_tool_start(
        {"name": "alerts_list_alerts"},
        "",
        run_id=run_id,
        name="alerts_list_alerts",
        inputs={"keyword": "local"},
    )
    message = AIMessageChunk(content="告警为空")
    await bridge.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=message)]]),
        run_id=run_id,
    )

    first = queue.get_nowait()
    second = queue.get_nowait()
    third = queue.get_nowait()

    assert first["event"] == "on_chat_model_stream"
    assert first["data"]["chunk"].content == "你"
    assert second["event"] == "on_tool_start"
    assert second["name"] == "alerts_list_alerts"
    assert "opspilot_step_index" not in (second.get("metadata") or {})
    assert second["data"]["input"] == {"keyword": "local"}
    assert third["event"] == "on_chat_model_end"
    assert third["data"]["output"].content == "告警为空"


@pytest.mark.asyncio
async def test_bridge_skips_tool_chunks_and_tool_end_messages():
    queue = asyncio.Queue()
    bridge = nested_agent_callbacks(_config_with_queue(queue))[0]
    run_id = uuid.uuid4()
    await bridge.on_llm_new_token(
        "",
        chunk=ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                tool_call_chunks=[{"id": "call-1", "name": "alerts_list_alerts", "args": ""}],
            )
        ),
        run_id=run_id,
    )
    await bridge.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessageChunk(
                            content="",
                            tool_calls=[{"id": "call-1", "name": "alerts_list_alerts", "args": {"keyword": "web-1"}}],
                        )
                    )
                ]
            ]
        ),
        run_id=run_id,
    )
    assert queue.empty()


def test_isolated_child_context_keeps_parent_handler_out_of_merge():
    parent = _AstreamEventsCallbackHandler()
    queue = asyncio.Queue()
    token = var_child_runnable_config.set({"callbacks": [parent], "configurable": {"thread_id": "t"}})
    try:
        with isolated_child_callback_context():
            merged = merge_configs(
                var_child_runnable_config.get(),
                {"callbacks": nested_agent_callbacks(_config_with_queue(queue))},
            )
        handlers = list(merged["callbacks"])
        assert parent not in handlers
        assert any(isinstance(handler, OwnedEventBridge) for handler in handlers)
        restored = var_child_runnable_config.get()
    finally:
        var_child_runnable_config.reset(token)
    assert restored is not None
    assert restored["callbacks"] == [parent]


def test_publish_node_finished_enqueues_terminal_event():
    queue = asyncio.Queue()
    publish_node_finished({"configurable": {OWNED_EVENT_QUEUE_KEY: queue}})
    assert queue.get_nowait()["event"] == NODE_FINISHED_EVENT
    publish_node_finished({})


def test_repeated_successful_tool_call_is_denied():
    request = type(
        "Req",
        (),
        {
            "tool_call": {"id": "call-2", "name": "alerts_list_alerts", "args": {"keyword": "web-1"}},
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "call-1", "name": "alerts_list_alerts", "args": {"keyword": "web-1"}}],
                ),
                ToolMessage(content='{"success": true}', tool_call_id="call-1", name="alerts_list_alerts"),
            ],
        },
    )()
    denied = repeated_successful_tool_denial(request)
    assert denied is not None
    assert POLICY_RESULT_MARKER in denied.content
    assert denied.tool_call_id == "call-2"


@pytest.mark.asyncio
async def test_owned_bridge_stamps_planned_step_index():
    queue = asyncio.Queue()
    config = _config_with_queue(queue)
    bridge = nested_agent_callbacks(config)[0]
    run_id = uuid.uuid4()
    with bind_planned_step_index(2, config):
        await bridge.on_tool_start(
            {"name": "cmdb_search_instances"},
            "",
            run_id=run_id,
            name="cmdb_search_instances",
            inputs={"ip": "10.10.41.149"},
        )
    event = queue.get_nowait()
    assert event["metadata"]["opspilot_step_index"] == 2


@pytest.mark.asyncio
async def test_bridge_keeps_step_stamp_after_ainvoke_context_exits():
    """工具回调常晚于 ainvoke 返回；退出 bind 后仍应盖上本步步骤号。"""
    queue = asyncio.Queue()
    config = _config_with_queue(queue)
    bridge = nested_agent_callbacks(config)[0]
    with bind_planned_step_index(3, config):
        pass
    await bridge.on_tool_start(
        {"name": "log_search_structured"},
        "",
        run_id=uuid.uuid4(),
        name="log_search_structured",
        inputs={},
    )
    event = queue.get_nowait()
    assert event["metadata"]["opspilot_step_index"] == 3


@pytest.mark.asyncio
async def test_owned_bridge_forwards_user_choice_custom_event():
    queue = asyncio.Queue()
    bridge = nested_agent_callbacks(_config_with_queue(queue))[0]
    payload = {"choice_id": "abc", "title": "您想查询哪边的告警？", "options": [{"key": "monitor", "label": "监控侧"}]}
    await bridge.on_custom_event("user_choice_request", payload, run_id=uuid.uuid4())
    event = queue.get_nowait()
    assert event["event"] == "on_custom_event"
    assert event["name"] == "user_choice_request"
    assert event["data"]["choice_id"] == "abc"


def test_publish_owned_custom_event_uses_configurable_queue():
    queue = asyncio.Queue()
    payload = {"choice_id": "result-1", "selected": ["监控侧"], "source": "user"}
    assert publish_owned_custom_event(_config_with_queue(queue), "user_choice_result", payload) is True
    event = queue.get_nowait()
    assert event["name"] == "user_choice_result"
    assert event["data"]["selected"] == ["监控侧"]
    assert publish_owned_custom_event({}, "user_choice_request", payload) is False
    assert queue.empty()


def test_publish_owned_custom_event_does_not_use_process_global_fallback():
    """空 config 不得回退到其他会话的队列。"""
    queue = asyncio.Queue()
    ctx = make_owned_stream_context(queue)
    config = attach_owned_stream_context({"configurable": {}}, ctx)
    assert publish_owned_custom_event(config, "user_choice_request", {"choice_id": "own"}) is True
    assert publish_owned_custom_event({}, "user_choice_request", {"choice_id": "leak"}) is False
    event = queue.get_nowait()
    assert event["data"]["choice_id"] == "own"
    assert queue.empty()


@pytest.mark.asyncio
async def test_bridge_stamps_step_from_shared_holder_without_contextvar():
    queue = asyncio.Queue()
    config = _config_with_queue(queue)
    bridge = nested_agent_callbacks(config)[0]
    holder = config["configurable"][PLANNED_STEP_HOLDER_KEY]

    holder["step_index"] = 1
    await bridge.on_tool_start({"name": "monitor_list_active_alerts"}, "", run_id=uuid.uuid4(), name="monitor_list_active_alerts", inputs={})
    holder["step_index"] = 2
    await bridge.on_tool_start({"name": "alerts_list_alerts"}, "", run_id=uuid.uuid4(), name="alerts_list_alerts", inputs={})

    first = queue.get_nowait()
    second = queue.get_nowait()
    assert first["metadata"]["opspilot_step_index"] == 1
    assert second["metadata"]["opspilot_step_index"] == 2


def test_remember_planned_tool_steps_records_model_ids():
    bindings: dict[str, int] = {}
    remember_planned_tool_steps(
        {"configurable": {"planned_tool_steps": bindings}},
        1,
        [ToolMessage(content="ok", tool_call_id="call-1", name="cmdb_search_instances")],
    )
    assert bindings == {"call-1": 1}


def _stream_config(queue=None):
    ctx = make_owned_stream_context(queue if queue is not None else asyncio.Queue())
    return attach_owned_stream_context({"configurable": {}}, ctx), ctx


@pytest.mark.asyncio
async def test_overlapping_streams_do_not_cross_session_choice_or_step():
    """同进程两条重叠流交叉写，选择卡和步骤号不得串会话。"""
    config_a, ctx_a = _stream_config()
    config_b, ctx_b = _stream_config()

    async def run_stream(config, ctx, choice_id, step_index, tool_call_id):
        with bind_planned_step_index(step_index, config):
            assert publish_owned_custom_event(config, "user_choice_request", {"choice_id": choice_id}) is True
            await asyncio.sleep(0.01)
            remember_planned_tool_steps(
                config,
                step_index,
                [ToolMessage(content="ok", tool_call_id=tool_call_id, name="alerts_list_alerts")],
            )
            assert publish_owned_custom_event(
                config,
                "user_choice_result",
                {"choice_id": choice_id, "selected": [choice_id]},
            ) is True
            return (
                lookup_planned_tool_step(tool_call_id, ctx),
                current_planned_step_index(ctx),
                lookup_planned_tool_step("call-a" if tool_call_id == "call-b" else "call-b", ctx),
            )

    (step_a, holder_a, leaked_a), (step_b, holder_b, leaked_b) = await asyncio.gather(
        run_stream(config_a, ctx_a, "aaa", 1, "call-a"),
        run_stream(config_b, ctx_b, "bbb", 9, "call-b"),
    )
    assert (step_a, holder_a, leaked_a) == (1, 1, None)
    assert (step_b, holder_b, leaked_b) == (9, 9, None)

    choices_a = []
    while not ctx_a.queue.empty():
        choices_a.append(ctx_a.queue.get_nowait()["data"]["choice_id"])
    choices_b = []
    while not ctx_b.queue.empty():
        choices_b.append(ctx_b.queue.get_nowait()["data"]["choice_id"])
    assert choices_a == ["aaa", "aaa"]
    assert choices_b == ["bbb", "bbb"]
    assert publish_owned_custom_event({}, "user_choice_request", {"choice_id": "zzz"}) is False
    assert ctx_a.queue.empty()
    assert ctx_b.queue.empty()


@pytest.mark.asyncio
async def test_overlapping_bridges_stamp_own_step_not_peer_holder():
    config_a, ctx_a = _stream_config()
    config_b, ctx_b = _stream_config()
    bridge_a = nested_agent_callbacks(config_a)[0]
    bridge_b = nested_agent_callbacks(config_b)[0]
    ctx_a.step_holder["step_index"] = 2
    ctx_b.step_holder["step_index"] = 7
    await asyncio.gather(
        bridge_a.on_tool_start({"name": "alerts_list_alerts"}, "", run_id=uuid.uuid4(), name="alerts_list_alerts", inputs={}),
        bridge_b.on_tool_start({"name": "cmdb_search_instances"}, "", run_id=uuid.uuid4(), name="cmdb_search_instances", inputs={}),
    )
    assert ctx_a.queue.get_nowait()["metadata"]["opspilot_step_index"] == 2
    assert ctx_b.queue.get_nowait()["metadata"]["opspilot_step_index"] == 7
