"""
Tests for timeout circuit breaker (Phase 2 #21).

Verifies:
- Total timeout: agent stops after cumulative time exceeds threshold
- Step timeout: individual tool execution timeout returns error ToolMessage
- LLM timeout: LLM call timeout returns graceful message
- Disabled config: no timeout enforcement
"""

import sys
import time
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
_falkordb.Graph = type("Graph", (), {})
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
_falkordb_asyncio.FalkorDB = type("FalkorDB", (), {})
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

import asyncio  # noqa: E402
from typing import Annotated  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def fast_tool(query: str) -> str:
    """A tool that returns instantly."""
    return f"result: {query}"


@tool
async def slow_async_tool(query: str) -> str:
    """A tool that sleeps (simulates slow execution)."""
    await asyncio.sleep(10)  # will be timed out
    return f"slow result: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools=None, mock_llm_delay=0):
    """Build ReAct graph, run with mock LLM."""
    if tools is None:
        tools = [fast_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools

    call_count = {"n": 0}
    responses = list(mock_llm_responses)

    async def mock_ainvoke(messages, *args, **kwargs):
        if mock_llm_delay > 0:
            await asyncio.sleep(mock_llm_delay)
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

    config = {"configurable": {"graph_request": request, "trace_id": "test"}}

    with (
        patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
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

    return result.get("messages", []), call_count["n"]


# ---------------------------------------------------------------------------
# Tests: Total Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTotalTimeout:
    """Total execution timeout."""

    async def test_total_timeout_triggers(self):
        """Total timeout triggers after elapsed time exceeds threshold."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0.05,  # 50ms - will trigger after first step
                step_timeout_seconds=0,
                llm_timeout_seconds=0,
            ),
        )
        responses = [
            AIMessage(content="Step1", tool_calls=[{"name": "fast_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Step2", tool_calls=[{"name": "fast_tool", "args": {"query": "y"}, "id": "c2"}]),
            AIMessage(content="Step3", tool_calls=[{"name": "fast_tool", "args": {"query": "z"}, "id": "c3"}]),
        ]

        # Add a small delay to simulate time passing

        original_monotonic = time.monotonic

        call_count = {"n": 0}

        def fast_forward_monotonic():
            """Each call advances time by 0.03s to trigger total timeout."""
            call_count["n"] += 1
            # First call: start_time set. Subsequent calls: add artificial time.
            return original_monotonic() + (call_count["n"] * 0.03)

        with patch("time.monotonic", side_effect=fast_forward_monotonic):
            messages, steps = await _build_and_run(request, responses)

        # Should have stopped before all 3 steps (total timeout)
        # Step 1: start_time set (no check). Step 2: elapsed > 0.05 -> timeout
        assert steps <= 2, f"Expected <= 2 steps due to total timeout, got {steps}"
        assert any("超时" in str(getattr(m, "content", "")) for m in messages)

    async def test_total_timeout_disabled(self):
        """total_timeout_seconds=0 means no total timeout."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=0,
                llm_timeout_seconds=0,
            ),
        )
        responses = [
            AIMessage(content="Step1", tool_calls=[{"name": "fast_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, steps = await _build_and_run(request, responses)
        assert steps == 2  # runs normally


# ---------------------------------------------------------------------------
# Tests: Step Timeout (Tool Execution)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStepTimeout:
    """Per-step tool execution timeout."""

    async def test_slow_tool_times_out(self):
        """Async tool that sleeps gets timed out."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=0.05,  # 50ms timeout
                llm_timeout_seconds=0,
            ),
        )
        responses = [
            AIMessage(content="Calling", tool_calls=[{"name": "slow_async_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Tool timed out, giving up."),
        ]

        messages, steps = await _build_and_run(request, responses, tools=[slow_async_tool])

        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any("超时" in str(m.content) for m in tool_msgs)

    async def test_fast_tool_no_timeout(self):
        """Fast tool completes within timeout."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=10.0,  # generous
                llm_timeout_seconds=0,
            ),
        )
        responses = [
            AIMessage(content="Calling", tool_calls=[{"name": "fast_tool", "args": {"query": "hi"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, steps = await _build_and_run(request, responses, tools=[fast_tool])
        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any("result: hi" in str(m.content) for m in tool_msgs)


# ---------------------------------------------------------------------------
# Tests: LLM Call Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLLMTimeout:
    """LLM call timeout."""

    async def test_llm_timeout_triggers(self):
        """LLM call that takes too long returns timeout message."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=0,
                llm_timeout_seconds=0.05,  # 50ms
            ),
        )
        responses = [AIMessage(content="Should not reach")]

        messages, steps = await _build_and_run(request, responses, mock_llm_delay=1.0)  # 1s delay > 50ms timeout

        # LLM timed out on first call
        assert steps == 0  # mock_ainvoke never completed
        assert any("超时" in str(getattr(m, "content", "")) for m in messages)

    async def test_llm_no_timeout_when_fast(self):
        """Fast LLM completes normally."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=0,
                llm_timeout_seconds=10.0,
            ),
        )
        responses = [AIMessage(content="Done.")]

        messages, steps = await _build_and_run(request, responses, mock_llm_delay=0)
        assert steps == 1


# ---------------------------------------------------------------------------
# Tests: Disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTimeoutDisabled:
    """Timeout completely disabled."""

    async def test_disabled_no_timeout(self):
        """When timeout_config.enabled=False, no timeout enforcement."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [
            AIMessage(content="Step1", tool_calls=[{"name": "fast_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, steps = await _build_and_run(request, responses)
        assert steps == 2

    async def test_step_timeout_zero_no_limit(self):
        """step_timeout_seconds=0 means no step timeout enforcement."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config={"enabled": False},
            timeout_config=TimeoutConfig(
                enabled=True,
                total_timeout_seconds=0,
                step_timeout_seconds=0,
                llm_timeout_seconds=0,
            ),
        )
        responses = [
            AIMessage(content="Step1", tool_calls=[{"name": "fast_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        with patch("asyncio.wait_for", side_effect=AssertionError("wait_for should not be called")):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2
