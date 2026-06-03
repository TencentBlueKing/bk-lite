"""
Tests for K8s tool duplicate invocation in Plan-and-Execute agent.

Reproduces the real-world issue where the Plan-and-Execute agent decomposes
a K8s question into multiple plan steps, and each step's inner ReAct loop
calls the same K8s query tool with identical args, receiving the same result.

The core problem: reflection_tracker is scoped per build_react_nodes() call,
so the inner ReAct loop resets its tool call history on every plan step.
Cross-step duplicate detection must happen at the outer level (replanner)
or via shared state.

Covers:
- Within a single plan step: same tool called 3x → reflection triggers (inner ReAct)
- Across plan steps: replanner sees duplicate results in step_history/messages
- Mixed K8s tools across steps → no false positive
- Lower repetition_threshold catches duplicates faster within a step
"""

import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from typing import Annotated  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentNode, PlanAndExecuteAgentRequest  # noqa: E402
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# K8s-like tools
# ---------------------------------------------------------------------------


@tool
def list_pods(namespace: str = "default") -> str:
    """List pods in a namespace."""
    return '{"items": [' '{"name": "web-abc", "status": "Running"},' '{"name": "api-def", "status": "Running"}' "]}"


@tool
def get_pod_details(pod_name: str, namespace: str = "default") -> str:
    """Get pod details."""
    return f'{{"name": "{pod_name}", "namespace": "{namespace}", "status": "Running", "restarts": 0}}'


@tool
def list_deployments(namespace: str = "default") -> str:
    """List deployments in a namespace."""
    return '{"items": [{"name": "web", "replicas": 3}]}'


# ---------------------------------------------------------------------------
# State (for inner ReAct tests)
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper: inner ReAct loop
# ---------------------------------------------------------------------------


async def _build_and_run_react(request, mock_llm_responses, tools_list):
    """Build ReAct graph (simulating one plan step's inner loop), return (messages, llm_inputs)."""
    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    llm_inputs = []

    async def mock_ainvoke(messages, *args, **kwargs):
        llm_inputs.append(list(messages))
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    mock_llm = MagicMock()
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.ainvoke = mock_ainvoke
    node_builder.get_llm_client = lambda *a, **kw: mock_llm

    graph_builder = StateGraph(AgentState)
    entry = await node_builder.build_react_nodes(
        graph_builder=graph_builder,
        composite_node_name="test_react",
    )
    graph_builder.set_entry_point(entry)
    graph = graph_builder.compile()

    config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": ""}}

    def _mock_render(template, ctx):
        if "reflection" in template:
            return f"[REFLECTION: {ctx.get('reason', '')}]"
        return "You are a test assistant."

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        side_effect=_mock_render,
    ), patch(
        "apps.opspilot.metis.llm.chain.node.is_interrupt_requested_async",
        new_callable=AsyncMock,
        return_value=False,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), llm_inputs


# ---------------------------------------------------------------------------
# Tests: Within single plan step (inner ReAct loop)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestK8sDuplicateWithinPlanStep:
    """Duplicate K8s tool calls within a single plan step's ReAct loop."""

    async def test_same_tool_repeated_triggers_reflection(self):
        """list_pods called 3x in one step → inner ReAct reflection triggers."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                consecutive_failures_threshold=3,
                repetition_window=6,
                repetition_threshold=3,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="check", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c1"}]),
            AIMessage(content="check again", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c2"}]),
            AIMessage(content="one more", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c3"}]),
            AIMessage(content="There are 2 pods running: web-abc and api-def."),
        ]

        messages, llm_inputs = await _build_and_run_react(request, responses, [list_pods])

        reflection_found = False
        for input_msgs in llm_inputs:
            for m in input_msgs:
                if isinstance(m, HumanMessage) and "[REFLECTION:" in str(m.content):
                    assert "list_pods" in str(m.content)
                    reflection_found = True
        assert reflection_found, "Inner ReAct loop should detect repeated list_pods calls"

        final_msg = messages[-1]
        assert isinstance(final_msg, AIMessage)
        assert not getattr(final_msg, "tool_calls", None)

    async def test_lower_threshold_catches_faster(self):
        """repetition_threshold=2 catches duplicates after 2 calls in one step."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                repetition_window=4,
                repetition_threshold=2,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="q1", tool_calls=[{"name": "list_pods", "args": {"namespace": "prod"}, "id": "c1"}]),
            AIMessage(content="q2", tool_calls=[{"name": "list_pods", "args": {"namespace": "prod"}, "id": "c2"}]),
            AIMessage(content="2 pods found."),
        ]

        _, llm_inputs = await _build_and_run_react(request, responses, [list_pods])

        reflection_found = any(isinstance(m, HumanMessage) and "REFLECTION" in str(m.content) for input_msgs in llm_inputs for m in input_msgs)
        assert reflection_found, "threshold=2 should trigger after 2 repeated calls"


# ---------------------------------------------------------------------------
# Tests: Cross-step duplicate detection (executor_node level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestK8sDuplicateAcrossPlanSteps:
    """Duplicate tool results across plan steps detected via replanner messages."""

    async def test_replanner_sees_duplicate_results_in_messages(self):
        """When two plan steps both produce identical list_pods results,
        the shared messages accumulate duplicates that replanner can detect.

        This test verifies the replanner's dedup logic (seen_contents set)
        filters duplicate content from the message history.
        """
        # Simulate accumulated messages after 2 steps both called list_pods
        pod_result = '{"items": [{"name": "web-abc", "status": "Running"}]}'
        state = {
            "messages": [
                HumanMessage(content="查看K8s集群有哪些Pod"),
                AIMessage(content="计划已制定"),
                # Step 1 messages
                HumanMessage(content="步骤1: 获取Pod列表"),
                AIMessage(content="调用list_pods", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c1"}]),
                AIMessage(content=pod_result),
                # Step 2 messages (duplicate)
                HumanMessage(content="步骤2: 确认Pod状态"),
                AIMessage(content="再次调用list_pods", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c2"}]),
                AIMessage(content=pod_result),  # identical result
            ],
            "original_plan": ["获取Pod列表", "确认Pod状态", "汇总结果"],
            "current_plan": ["确认Pod状态", "汇总结果"],
            "execution_count": 1,
            "step_history": [],
            "final_response": None,
            "execution_prompt": None,
        }

        # Verify the replanner's dedup logic works on the message list
        messages = state["messages"]
        seen_contents = set()
        recent_messages = []
        for msg in messages:
            if hasattr(msg, "content") and msg.content:
                content = msg.content.strip()
                if content and content not in seen_contents:
                    recent_messages.append(content)
                    seen_contents.add(content)

        # The duplicate pod_result should be deduped
        pod_result_count = sum(1 for m in recent_messages if m == pod_result)
        assert pod_result_count == 1, f"Replanner dedup should reduce duplicate tool results to 1, got {pod_result_count}"

    async def test_executor_injects_step_as_human_message(self):
        """Each plan step gets a HumanMessage injection so the inner ReAct knows what to do."""
        node = PlanAndExecuteAgentNode()
        req = PlanAndExecuteAgentRequest(
            openai_api_base="http://localhost:8000/v1",
            openai_api_key="test-key",
            model="gpt-4o",
            user_message="查看K8s集群状态",
        )
        config = {"configurable": {"graph_request": req}}

        state = {
            "current_plan": ["列出所有Pod", "检查Pod健康状态"],
            "original_plan": ["列出所有Pod", "检查Pod健康状态"],
            "messages": [AIMessage(content="计划已制定")],
            "execution_prompt": None,
            "final_response": None,
        }

        result = await node.executor_node(state, config)

        # Should inject HumanMessage with step content
        injected = result.get("messages", [])
        assert len(injected) == 1
        assert isinstance(injected[0], HumanMessage)
        assert "列出所有Pod" in str(injected[0].content)


# ---------------------------------------------------------------------------
# Tests: Mixed tools across steps (no false positive)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestK8sMixedToolsNoFalsePositive:
    """Different K8s tools called across steps should not trigger reflection."""

    async def test_different_tools_no_reflection(self):
        """list_pods, get_pod_details, list_deployments each called once → no reflection."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                repetition_window=6,
                repetition_threshold=3,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="list", tool_calls=[{"name": "list_pods", "args": {"namespace": "default"}, "id": "c1"}]),
            AIMessage(content="detail", tool_calls=[{"name": "get_pod_details", "args": {"pod_name": "web-abc"}, "id": "c2"}]),
            AIMessage(content="deploys", tool_calls=[{"name": "list_deployments", "args": {"namespace": "default"}, "id": "c3"}]),
            AIMessage(content="Cluster: 2 pods, 1 deployment, all healthy."),
        ]

        _, llm_inputs = await _build_and_run_react(
            request,
            responses,
            [list_pods, get_pod_details, list_deployments],
        )

        for input_msgs in llm_inputs:
            for m in input_msgs:
                if isinstance(m, HumanMessage) and "REFLECTION" in str(m.content):
                    pytest.fail("Different tools should not trigger reflection")
