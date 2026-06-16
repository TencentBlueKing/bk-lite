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

from langchain_core.messages import ToolMessage as _TM

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

    with (
        patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            side_effect=_mock_render,
        ),
        patch(
            "apps.opspilot.metis.llm.chain.node.is_interrupt_requested_async",
            new_callable=AsyncMock,
            return_value=False,
        ),
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
                # 本用例验证软反思提示，关闭硬拦截避免第 3 次调用被直接阻断
                duplicate_call_hard_enabled=False,
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
# Tests: Hard interception of identical (name + args) duplicate calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDuplicateCallHardBlock:
    """同名同参工具调用累计达阈值后被硬拦截、不再真正执行。"""

    async def test_identical_call_blocked_after_limit(self):
        """list_pods 用完全相同参数调用 4 次：前 3 次执行，第 4 次被硬拦截。"""
        call_counter = {"n": 0}

        @tool
        def counting_list_pods(namespace: str = "default") -> str:
            """List pods, counting how many times the tool actually runs."""
            call_counter["n"] += 1
            return '{"items": [{"name": "web-abc", "status": "Running"}]}'

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                # 关闭软反思的重置干扰，仅验证硬拦截
                repetition_window=99,
                repetition_threshold=99,
                duplicate_call_hard_enabled=True,
                duplicate_call_hard_limit=3,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        same_args = {"namespace": "default"}
        responses = [
            AIMessage(content="c1", tool_calls=[{"name": "counting_list_pods", "args": same_args, "id": "c1"}]),
            AIMessage(content="c2", tool_calls=[{"name": "counting_list_pods", "args": same_args, "id": "c2"}]),
            AIMessage(content="c3", tool_calls=[{"name": "counting_list_pods", "args": same_args, "id": "c3"}]),
            AIMessage(content="c4", tool_calls=[{"name": "counting_list_pods", "args": same_args, "id": "c4"}]),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run_react(request, responses, [counting_list_pods])

        # 工具真正执行只发生 3 次，第 4 次被拦截
        assert call_counter["n"] == 3, f"工具应只执行 3 次，实际 {call_counter['n']} 次"

        # 第 4 次调用对应的 tool_call_id=c4 应有一条 [已拦截] 的 ToolMessage 配对

        blocked = [m for m in messages if isinstance(m, _TM) and getattr(m, "tool_call_id", "") == "c4"]
        assert blocked, "第 4 次重复调用应返回配对的 ToolMessage"
        assert "[已拦截]" in str(blocked[0].content), "第 4 次调用应被硬拦截"

    async def test_same_batch_duplicates_collapsed_to_one(self):
        """LLM 在一条消息里并行发出 3 个完全相同的调用：在 agent_node 源头去重，
        提交的 AIMessage 只剩 1 个 tool_call（等价于前端只渲染 1 张卡片），且工具只执行 1 次。

        复现截图：3 个相同 generate_repair_report 同时转圈。根因是每个 tool_call 都会在
        流式层各触发一个 TOOL_CALL_START → 前端渲染 3 张卡片。由于 agui_stream 严格按
        AIMessage.tool_calls 数量发 START，只要提交的 AIMessage 只剩 1 个 tool_call，
        前端就只会有 1 张卡片。
        """
        call_counter = {"n": 0}

        @tool
        def batch_list_pods(namespace: str = "default") -> str:
            """List pods, counting how many times the tool actually runs."""
            call_counter["n"] += 1
            return '{"items": [{"name": "web-abc", "status": "Running"}]}'

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                repetition_window=99,
                repetition_threshold=99,
                duplicate_call_hard_enabled=True,
                duplicate_call_hard_limit=3,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        same_args = {"namespace": "default"}
        responses = [
            # 一条 AIMessage 同时发出 3 个完全相同的 tool_calls（复现截图场景）
            AIMessage(
                content="batch",
                tool_calls=[
                    {"name": "batch_list_pods", "args": same_args, "id": "b1"},
                    {"name": "batch_list_pods", "args": same_args, "id": "b2"},
                    {"name": "batch_list_pods", "args": same_args, "id": "b3"},
                ],
            ),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run_react(request, responses, [batch_list_pods])

        # 同批次 3 个相同调用只真正执行 1 次
        assert call_counter["n"] == 1, f"同批次重复应只执行 1 次，实际 {call_counter['n']} 次"

        # agent_node 源头去重：提交到 state 的那条 AIMessage 只应保留 1 个 tool_call
        ai_with_tc = [
            m for m in messages if isinstance(m, AIMessage) and getattr(m, "tool_calls", None) and m.tool_calls[0].get("name") == "batch_list_pods"
        ]
        assert ai_with_tc, "应存在一条调用 batch_list_pods 的 AIMessage"
        assert len(ai_with_tc[0].tool_calls) == 1, f"同批次重复应在源头去重为 1 个 tool_call，实际 {len(ai_with_tc[0].tool_calls)} 个"

        # 只生成 1 条 ToolMessage（b1），不应有 b2/b3 的孤儿 tool 结果

        tool_msgs = [m for m in messages if isinstance(m, _TM)]
        assert len(tool_msgs) == 1, f"应只生成 1 条 ToolMessage，实际 {len(tool_msgs)} 条"
        assert "web-abc" in str(tool_msgs[0].content)

    async def test_different_args_not_blocked(self):
        """同名工具但参数不同（不同签名）不应被拦截。"""
        call_counter = {"n": 0}

        @tool
        def ns_list_pods(namespace: str = "default") -> str:
            """List pods in a namespace."""
            call_counter["n"] += 1
            return '{"items": []}'

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                repetition_window=99,
                repetition_threshold=99,
                duplicate_call_hard_enabled=True,
                duplicate_call_hard_limit=3,
            ),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="a", tool_calls=[{"name": "ns_list_pods", "args": {"namespace": "a"}, "id": "c1"}]),
            AIMessage(content="b", tool_calls=[{"name": "ns_list_pods", "args": {"namespace": "b"}, "id": "c2"}]),
            AIMessage(content="c", tool_calls=[{"name": "ns_list_pods", "args": {"namespace": "c"}, "id": "c3"}]),
            AIMessage(content="d", tool_calls=[{"name": "ns_list_pods", "args": {"namespace": "d"}, "id": "c4"}]),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run_react(request, responses, [ns_list_pods])

        # 4 次参数各不相同，全部执行，无拦截
        assert call_counter["n"] == 4, f"不同参数应全部执行，实际 {call_counter['n']} 次"

        assert not any("[已拦截]" in str(getattr(m, "content", "")) for m in messages if isinstance(m, _TM))


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
