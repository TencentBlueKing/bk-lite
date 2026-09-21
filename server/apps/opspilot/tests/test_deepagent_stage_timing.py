"""DeepAgent 阶段耗时日志：区分规划模型慢还是规划拆步不合理。"""

import asyncio
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from apps.opspilot.metis.llm.agent.stage_timing import STAGE_TIMING_LOG, bound_thread_id, log_stage_timing
from apps.opspilot.metis.llm.agent.tool_execution_planner import ToolExecutionPlanner
from apps.opspilot.metis.llm.chain.node import ToolsNodes
from apps.opspilot.tests.test_deepagent_engine_service import _FakeGraphBuilder, _request, _tool

pytestmark = pytest.mark.unit

_PAYLOAD_SENTINEL = "TOKEN_PAYLOAD_SENTINEL"


def _stage_records(caplog):
    return [record for record in caplog.records if record.name == "opspilot" and record.msg == STAGE_TIMING_LOG]


def _stage_map(caplog):
    return {record.args[0]: record for record in _stage_records(caplog)}


class _Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_stage_timing_template_omits_payload_and_renders(caplog):
    caplog.set_level(logging.INFO, logger="opspilot")
    log_stage_timing(
        "planning",
        2500,
        thread_id=f"thread-1\n{_PAYLOAD_SENTINEL}",
        step_count=0,
        model_call_ms=2400,
    )

    records = _stage_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.args == (
        "planning",
        2500,
        bound_thread_id(f"thread-1 {_PAYLOAD_SENTINEL}"),
        0,
        0,
        0,
        0,
        0,
        2400,
        0,
    )
    message = record.getMessage()
    assert message.startswith("event=deepagent_stage_timing stage=planning duration_ms=2500 ")
    assert "step_count=0" in message
    assert "model_call_ms=2400" in message
    assert "\n" not in message
    formatted = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
    assert _PAYLOAD_SENTINEL in formatted


@pytest.mark.asyncio
async def test_planner_greeting_logs_empty_steps_and_model_call_ms(monkeypatch, caplog):
    clock = _Clock()
    monkeypatch.setattr("apps.opspilot.metis.llm.agent.stage_timing.time.monotonic", clock.monotonic)
    caplog.set_level(logging.INFO, logger="opspilot")

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            clock.advance(2.5)
            return AIMessage(content='{"goal":"问候","steps":[]}')

    tools = [_tool("cmdb_search_instances"), _tool("monitor_query_metrics")]
    plan = await ToolExecutionPlanner(FakeLLM()).plan(
        f"你好 {_PAYLOAD_SENTINEL}",
        tools,
        thread_id="thread-hello",
    )

    assert plan.steps == []
    record = _stage_map(caplog)["planning"]
    assert record.args[1] == 2500
    assert record.args[2] == "thread-hello"
    assert record.args[3] == 0
    assert record.args[8] == 2500
    rendered = record.getMessage()
    assert _PAYLOAD_SENTINEL not in rendered
    assert _PAYLOAD_SENTINEL not in logging.Formatter("%(message)s").format(record)


@pytest.mark.asyncio
async def test_planner_retry_counts_both_model_calls(monkeypatch, caplog):
    clock = _Clock()
    monkeypatch.setattr("apps.opspilot.metis.llm.agent.stage_timing.time.monotonic", clock.monotonic)
    caplog.set_level(logging.INFO, logger="opspilot")
    calls = []

    class FakeLLM:
        async def ainvoke(self, messages, config=None):
            calls.append(messages)
            clock.advance(1.0 if len(calls) == 1 else 2.0)
            if len(calls) == 1:
                return AIMessage(content="It looks like your message came through empty!")
            return AIMessage(content='{"goal":"问候","steps":[]}')

    plan = await ToolExecutionPlanner(FakeLLM()).plan("你好", [_tool("cmdb_search_instances")])
    assert plan.steps == []
    record = _stage_map(caplog)["planning"]
    assert record.args[6] == 1
    assert record.args[8] == 3000


def test_hello_with_builtin_tools_logs_planning_then_lightweight_reply(monkeypatch, caplog):
    clock = _Clock()
    monkeypatch.setattr("apps.opspilot.metis.llm.agent.stage_timing.time.monotonic", clock.monotonic)
    caplog.set_level(logging.INFO, logger="opspilot")

    node = ToolsNodes()
    node.all_tools = [_tool("cmdb_search_instances"), _tool("monitor_query_metrics")]
    req = _request(user_message=f"你好 {_PAYLOAD_SENTINEL}", thread_id="thread-hello")

    gb = _FakeGraphBuilder()
    name = asyncio.run(node.build_deepagent_nodes(gb, composite_node_name="deep_agent"))
    wrapper = gb.nodes[name]

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            joined = "\n".join(str(getattr(message, "content", "") or "") for message in messages)
            is_planner = "工具执行规划器" in joined or "紧凑工具目录" in joined
            clock.advance(1.5 if is_planner else 0.8)
            if is_planner:
                return AIMessage(content=json.dumps({"goal": "问候", "steps": []}, ensure_ascii=False))
            return AIMessage(content="你好！")

    with (
        patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None),
        patch.object(ToolsNodes, "_build_skill_backend_and_sources", return_value=(None, [], None)),
        patch.object(ToolsNodes, "_collect_deepagent_tools", return_value=node.all_tools),
        patch.object(ToolsNodes, "get_llm_client", return_value=_FakeLLM()),
    ):
        result = asyncio.run(
            wrapper(
                {"messages": [HumanMessage(content=f"你好 {_PAYLOAD_SENTINEL}")]},
                {"configurable": {"graph_request": req}},
            )
        )

    assert result["messages"][0].content == "你好！"
    stages = _stage_map(caplog)
    planning = stages["planning"]
    reply = stages["lightweight_reply"]
    assert planning.args[1] == 1500
    assert planning.args[3] == 0
    assert planning.args[8] == 1500
    assert planning.args[2] == "thread-hello"
    assert reply.args[1] == 800
    assert "plan_step" not in stages
    rendered = "\n".join(record.getMessage() for record in _stage_records(caplog))
    assert _PAYLOAD_SENTINEL not in rendered


def test_planned_step_logs_step_and_run_timing(monkeypatch, caplog):
    clock = _Clock()
    monkeypatch.setattr("apps.opspilot.metis.llm.agent.stage_timing.time.monotonic", clock.monotonic)
    caplog.set_level(logging.INFO, logger="opspilot")

    node = ToolsNodes()
    node.all_tools = [_tool("cmdb_search_instances")]
    req = _request(user_message="这台机器纳管了吗", thread_id="thread-cmdb")

    gb = _FakeGraphBuilder()
    name = asyncio.run(node.build_deepagent_nodes(gb, composite_node_name="deep_agent"))
    wrapper = gb.nodes[name]
    fake_agent = MagicMock()
    agent_calls = {"count": 0}

    async def _ainvoke(payload, config=None):
        clock.advance(3.0)
        agent_calls["count"] += 1
        return {
            **payload,
            "messages": list(payload["messages"]) + [AIMessage(content=f"步骤结果 {agent_calls['count']}")],
        }

    fake_agent.ainvoke = _ainvoke

    class _FakeLLM:
        async def ainvoke(self, messages, config=None):
            clock.advance(1.0)
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "查纳管",
                        "steps": [{"objective": "查CMDB", "tools": ["cmdb_search_instances"]}],
                    },
                    ensure_ascii=False,
                )
            )

    with (
        patch.object(ToolsNodes, "_build_knowledge_retrieve_tool", return_value=None),
        patch.object(ToolsNodes, "_collect_deepagent_tools", return_value=node.all_tools),
        patch("apps.opspilot.metis.llm.chain.node.create_deep_agent", return_value=fake_agent),
        patch.object(ToolsNodes, "get_llm_client", return_value=_FakeLLM()),
    ):
        result = asyncio.run(
            wrapper(
                {"messages": [HumanMessage(content="这台机器纳管了吗")]},
                {"configurable": {"graph_request": req}},
            )
        )

    assert result["messages"]
    stages = _stage_map(caplog)
    assert stages["planning"].args[3] == 1
    assert stages["planning"].args[8] == 1000
    assert stages["plan_step"].args[1] == 3000
    assert stages["plan_step"].args[4] == 1
    assert stages["plan_step"].args[5] == 1
    assert stages["planned_summary"].args[1] == 3000
    assert stages["planned_run"].args[3] >= 1
    assert stages["planned_run"].args[9] == 1
    assert stages["planned_run"].args[2] == "thread-cmdb"
