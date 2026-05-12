"""
Tests for in-loop interrupt/cancellation (Phase 2 #20).

Verifies that:
- agent_node checks interrupt before LLM call and stops gracefully
- logged_tool_node checks interrupt before tool execution and returns placeholder ToolMessages
- No interrupt when execution_id is empty or flag not set
- Integration: interrupt mid-loop terminates within one step
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, RetryConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def slow_tool(query: str) -> str:
    """A tool that simulates slow execution."""
    return f"result: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools=None, execution_id="", interrupt_at_step=None):
    """Build ReAct graph with optional interrupt simulation.

    Args:
        interrupt_at_step: if set, is_interrupt_requested returns True starting from this step number
    """
    if tools is None:
        tools = [slow_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools

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

    extra_config = {}
    if execution_id:
        extra_config["execution_id"] = execution_id

    config = {
        "configurable": {
            "graph_request": request,
            "trace_id": "test",
            **extra_config,
        }
    }

    # Mock is_interrupt_requested based on step
    interrupt_check_count = {"n": 0}

    def mock_is_interrupt(exec_id):
        interrupt_check_count["n"] += 1
        if interrupt_at_step is not None and interrupt_check_count["n"] >= interrupt_at_step:
            return True
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInterruptInAgentNode:
    """Interrupt detected in agent_node before LLM call."""

    async def test_interrupt_on_first_step(self):
        """Interrupt requested before step 1 — agent returns immediately."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            AIMessage(content="Should not run", tool_calls=[{"name": "slow_tool", "args": {"query": "x"}, "id": "c1"}]),
        ]

        messages, steps = await _build_and_run(
            request,
            responses,
            execution_id="exec_123",
            interrupt_at_step=1,  # interrupt from first check
        )

        # LLM should never have been called
        assert steps == 0, f"Expected 0 LLM calls (interrupted before first), got {steps}"
        # Should have an interrupted message
        assert any("中断" in str(getattr(m, "content", "")) for m in messages)

    async def test_interrupt_on_second_step(self):
        """Step 1 runs normally, interrupt on step 2."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
        )
        responses = [
            AIMessage(content="Step1", tool_calls=[{"name": "slow_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Step2"),  # would be natural end, but won't reach
        ]

        # interrupt_at_step=2: first check (agent_node step 1) returns False,
        # second check (logged_tool_node step 1) returns True
        # OR third check (agent_node step 2) returns True
        # The counter increments on each call to is_interrupt_requested
        # agent_node step1: check 1 -> False
        # logged_tool_node step1: check 2 -> True (interrupt_at_step=2)
        messages, steps = await _build_and_run(
            request,
            responses,
            execution_id="exec_456",
            interrupt_at_step=2,
        )

        # Step 1 LLM ran, but tool node was interrupted
        assert steps == 1
        # Should have interrupted tool messages
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any("中断" in str(m.content) for m in tool_msgs)


@pytest.mark.asyncio
class TestInterruptInToolNode:
    """Interrupt detected in logged_tool_node before tool execution."""

    async def test_tool_node_returns_placeholder_messages(self):
        """When interrupted, tool node returns ToolMessages with [执行已中断] for each tool_call."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
        )
        # Two tool calls in one response
        responses = [
            AIMessage(
                content="Calling tools",
                tool_calls=[
                    {"name": "slow_tool", "args": {"query": "a"}, "id": "c1"},
                    {"name": "slow_tool", "args": {"query": "b"}, "id": "c2"},
                ],
            ),
            AIMessage(content="Done"),
        ]

        # interrupt_at_step=2: agent_node check (1) passes, tool_node check (2) triggers
        messages, steps = await _build_and_run(
            request,
            responses,
            execution_id="exec_789",
            interrupt_at_step=2,
        )

        # LLM ran once
        assert steps == 1
        # Should have 2 interrupted ToolMessages (one per tool_call)
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        interrupted_tools = [m for m in tool_msgs if "中断" in str(m.content)]
        assert len(interrupted_tools) == 2


@pytest.mark.asyncio
class TestNoInterrupt:
    """No interrupt when conditions don't apply."""

    async def test_no_execution_id_no_interrupt(self):
        """Without execution_id, interrupt is never checked."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "slow_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        # No execution_id, interrupt_at_step=1 would trigger if checked
        messages, steps = await _build_and_run(
            request,
            responses,
            execution_id="",  # empty
            interrupt_at_step=1,
        )

        # Should complete normally
        assert steps == 2

    async def test_no_interrupt_flag_runs_normally(self):
        """With execution_id but no interrupt flag, runs normally."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "slow_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, steps = await _build_and_run(
            request,
            responses,
            execution_id="exec_normal",
            interrupt_at_step=None,  # never interrupts
        )

        assert steps == 2
