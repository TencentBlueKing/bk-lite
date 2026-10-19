"""request_user_choice 发出即结束；校验失败不终止。"""

import asyncio
from types import SimpleNamespace

import pytest
from django.test import override_settings
from langchain_core.messages import AIMessage

from apps.opspilot.metis.llm.chain.nested_stream import OWNED_EVENT_QUEUE_KEY
from apps.opspilot.metis.llm.middleware.terminal_user_choice import TerminalUserChoiceMiddleware
from apps.opspilot.utils.pending_question import consume_pending_question

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "terminal-choice-tests",
    }
}


@pytest.fixture(autouse=True)
def _locmem_cache():
    with override_settings(CACHES=_LOCMEM):
        from django.core.cache import cache

        cache.clear()
        yield


class _Runtime:
    def __init__(self, configurable):
        self.config = {"configurable": configurable}


@pytest.mark.django_db
def test_valid_choice_ends_run_and_writes_visible_text():
    middleware = TerminalUserChoiceMiddleware()
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-choice",
                        "name": "request_user_choice",
                        "args": {"question": "选哪个集群", "question_type": "single_select", "options": ["a", "b"]},
                    }
                ],
            )
        ]
    }
    runtime = _Runtime({"execution_id": "exec-1", "node_id": "skill_test", "thread_id": "thread-ut"})
    result = middleware.after_model(state, runtime)

    assert result["jump_to"] == "end"
    assert result["messages"][0].content.startswith("已向用户发出选择")
    assert "选哪个集群" in result["messages"][1].content
    assert "1. a" in result["messages"][1].content
    pending = consume_pending_question("thread:thread-ut")
    assert pending["kind"] == "user_choice"
    assert pending["question_text"] == result["messages"][1].content


def test_guard_rejection_does_not_end_run(monkeypatch):
    middleware = TerminalUserChoiceMiddleware()
    monkeypatch.setattr(
        "apps.opspilot.metis.llm.middleware.terminal_user_choice.guard_rejection",
        lambda call, configurable: "选项不可信",
    )
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-choice",
                        "name": "request_user_choice",
                        "args": {"question": "选集群", "question_type": "single_select", "options": ["fake"]},
                    }
                ],
            )
        ]
    }
    assert middleware.after_model(state, _Runtime({})) is None


def test_choice_tool_description_mentions_turn_end():
    from apps.opspilot.metis.llm.chain.approval_tools import ApprovalToolsMixin

    tool = ApprovalToolsMixin._build_choice_tool(SimpleNamespace())
    assert "本轮对话结束" in tool.description


def test_answering_drops_choice_plan_and_skips_another_question():
    from langchain_core.messages import HumanMessage, ToolMessage

    from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlan, ToolExecutionStep, drop_type_choice_when_declared
    from apps.opspilot.metis.llm.common.tool_failure import step_has_unasked_missing_params

    history = [
        HumanMessage(content="查 cpu"),
        AIMessage(content="请选择对象类型\n\n1. 主机\n2. Pod"),
        HumanMessage(content="先看看别的"),
    ]
    plan = ToolExecutionPlan(
        goal="查",
        steps=[
            ToolExecutionStep(objective="问类型", tools=["request_user_choice"]),
            ToolExecutionStep(objective="查指标", tools=["monitor_query_metric_data", "request_user_choice"]),
        ],
    )
    cleaned = drop_type_choice_when_declared(plan, "先看看别的", history)
    assert [step.tools for step in cleaned.steps] == [["monitor_query_metric_data"]]
    missing = [ToolMessage(content="instance_ids is required", tool_call_id="1", name="query")]
    assert step_has_unasked_missing_params(missing, conversation_messages=history) is False
    assert step_has_unasked_missing_params(missing) is True


def test_pending_node_skips_intent_and_missing_node_falls_through():
    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

    engine = ChatFlowEngine.__new__(ChatFlowEngine)
    nodes = {
        "agent-b": {"id": "agent-b", "type": "agents"},
        "intent": {"id": "intent", "type": "intent_classification"},
    }
    engine._get_node_by_id = lambda node_id: nodes.get(node_id)
    engine._find_target_agent_node = lambda *args, **kwargs: (None, [nodes["intent"]])
    engine.set_start_node_variable = lambda data, start: {**data, "mapped": True}
    called = {"prereq": False}

    def _prereq(nodes_before, data):
        called["prereq"] = True
        return {**data, "intent_result": "other"}

    engine._execute_prerequisite_nodes = _prereq
    engine._find_agent_by_intent = lambda *args, **kwargs: {"id": "agent-a", "type": "agents"}

    target, mapped, error = ChatFlowEngine._resolve_sse_target_agent(
        engine,
        {"pending_question": {"node_id": "agent-b", "kind": "user_choice"}},
        {"id": "start", "type": "embedded_chat"},
        None,
        False,
        False,
    )
    assert error is None
    assert target["id"] == "agent-b"
    assert mapped["mapped"] is True
    assert called["prereq"] is False

    fallback, _, fallback_error = ChatFlowEngine._resolve_sse_target_agent(
        engine,
        {"pending_question": {"node_id": "deleted-node"}},
        {"id": "start", "type": "embedded_chat"},
        None,
        False,
        False,
    )
    assert fallback_error is None
    assert fallback["id"] == "agent-a"
    assert called["prereq"] is True


def test_unrelated_k8s_reply_is_not_a_repair_mode():
    from apps.opspilot.metis.llm.chain.node import ToolsNodes

    assert ToolsNodes._match_repair_group_reply("今天天气怎么样") is None
    assert ToolsNodes._match_repair_group_reply("按空间聚合") == "scope"


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_limit_continue_ends_turn_without_same_run_grant():
    from apps.opspilot.metis.llm.middleware.planned_execution_limits import PlannedExecutionLimitMiddleware, ask_limit_continue

    queue = asyncio.Queue()
    text, _tool_message = await ask_limit_continue(
        kind="model_calls",
        step_objective="查磁盘",
        config={
            "configurable": {
                "execution_id": "exec-limit",
                "node_id": "agent-b",
                "thread_id": "limit-thread",
                OWNED_EVENT_QUEUE_KEY: queue,
            }
        },
        messages=[],
        summary="磁盘已到 80%",
    )
    assert "1. 继续" in text
    assert "磁盘已到 80%" in text
    event = queue.get_nowait()
    assert event["name"] == "user_choice_request"
    assert event["data"]["options"]
    pending = consume_pending_question("thread:limit-thread")
    assert pending["kind"] == "limit_continue"
    assert pending["node_id"] == "agent-b"
    middleware = PlannedExecutionLimitMiddleware(run_limit=2, token_budget=0)
    assert not hasattr(middleware, "grant_continue")
