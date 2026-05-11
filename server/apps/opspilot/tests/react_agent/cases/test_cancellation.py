"""
Tests for #20 取消与优雅终止 (cancellation & graceful shutdown).

Verifies:
- agent_node checks is_interrupt_requested at each step start
- logged_tool_node checks interrupt before tool execution
- Interrupted agent returns AIMessage("任务已被中断。")
- Interrupted tool returns ToolMessage("[执行已中断]") for each pending tool_call
- No interrupt when execution_id is empty or not in cache
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
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def slow_tool(query: str) -> str:
    """A tool that takes time."""
    return f"done: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, interrupt_at_step=None, interrupt_at_tool=False, execution_id="exec-123"):
    """Build ReAct graph with optional interrupt simulation.

    Args:
        interrupt_at_step: step number at which is_interrupt_requested returns True
        interrupt_at_tool: if True, interrupt triggers during tool execution phase
    """
    node_builder = ToolsNodes()
    node_builder.tools = [slow_tool]

    call_count = {"n": 0}
    responses = list(mock_llm_responses)

    async def mock_ainvoke(messages, *args, **kwargs):
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

    config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": execution_id}}

    # Build interrupt mock logic
    call_sites = {"count": 0}

    def mock_is_interrupt(exec_id):
        if not exec_id:
            return False
        call_sites["count"] += 1
        if interrupt_at_step is None:
            return False
        if interrupt_at_tool:
            # Agent check is odd calls (1,3,5...), tool check is even calls (2,4,6...)
            # We want to NOT interrupt at agent, but interrupt at tool for the target step.
            # Each step has 2 calls: agent then tool. Step N = calls (2N-1, 2N).
            # For interrupt_at_step=1: interrupt on call #2 (tool of step 1).
            call_num = call_sites["count"]
            tool_call_num = interrupt_at_step * 2
            return call_num >= tool_call_num
        else:
            # Interrupt at agent_node entry for the target step
            # Each step: agent check first. Step N = call (2N-1) for agent, (2N) for tool.
            # But step 1's agent doesn't have a preceding tool check.
            # Actually: first call is always agent step 1. Then if it has tool_calls,
            # next is tool step 1, then agent step 2, etc.
            # Simplify: just count agent-level checks (odd-numbered calls in sequence)
            # But we can't distinguish agent vs tool here...
            # Simpler approach: interrupt on Nth call overall for agent-level interrupt.
            return call_sites["count"] >= interrupt_at_step
        return False

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ), patch(
        "apps.opspilot.metis.llm.chain.node.is_interrupt_requested",
        side_effect=mock_is_interrupt,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), call_count["n"]


# ---------------------------------------------------------------------------
# Tests: Agent-level interrupt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancellationAgentNode:
    """Interrupt detected at agent_node entry."""

    async def test_interrupt_at_step_1(self):
        """Interrupt before first LLM call — immediate termination."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [AIMessage(content="Should not run.")]

        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=1, interrupt_at_tool=False)

        # LLM never called
        assert llm_calls == 0
        # Final message indicates interruption
        last_content = str(getattr(messages[-1], "content", ""))
        assert "中断" in last_content

    async def test_interrupt_at_step_2(self):
        """Step 1 runs normally, step 2 is interrupted."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "slow_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="Should not run."),
        ]

        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=2, interrupt_at_tool=False)

        # First LLM call succeeded, second was interrupted
        assert llm_calls == 1
        last_content = str(getattr(messages[-1], "content", ""))
        assert "中断" in last_content

    async def test_no_interrupt_without_execution_id(self):
        """No execution_id — interrupt check skipped, runs normally."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [AIMessage(content="Done.")]

        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=1, execution_id="")

        # Runs fine since execution_id is empty
        assert llm_calls == 1


# ---------------------------------------------------------------------------
# Tests: Tool-level interrupt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCancellationToolNode:
    """Interrupt detected at logged_tool_node entry."""

    async def test_interrupt_before_tool_execution(self):
        """Tool execution is skipped, returns [执行已中断] ToolMessages."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "slow_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="Interrupted."),
        ]

        # Interrupt at tool phase of step 1
        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=1, interrupt_at_tool=True)

        # Tool was interrupted, but agent still gets to run after (with interrupted tool result)
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any("中断" in str(getattr(m, "content", "")) for m in tool_msgs)

    async def test_multiple_tool_calls_all_interrupted(self):
        """Multiple pending tool_calls — all get interrupted ToolMessages."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="multi",
                tool_calls=[
                    {"name": "slow_tool", "args": {"query": "a"}, "id": "c1"},
                    {"name": "slow_tool", "args": {"query": "b"}, "id": "c2"},
                ],
            ),
            AIMessage(content="Done."),
        ]

        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=1, interrupt_at_tool=True)

        # Both tool_calls should get interrupted ToolMessages
        interrupted_tool_msgs = [m for m in messages if isinstance(m, ToolMessage) and "中断" in str(getattr(m, "content", ""))]
        assert len(interrupted_tool_msgs) == 2


# ---------------------------------------------------------------------------
# Tests: No interrupt (normal flow)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNoInterrupt:
    """Normal execution without interrupts."""

    async def test_normal_flow_no_interrupt(self):
        """No interrupt requested — agent runs to completion."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "slow_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="All done."),
        ]

        messages, llm_calls = await _build_and_run(request, responses, interrupt_at_step=None)

        assert llm_calls == 2
        last_content = str(getattr(messages[-1], "content", ""))
        assert "All done" in last_content
        assert "中断" not in last_content
