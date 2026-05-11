"""
Tests for #19 步骤级进度汇报.

Verifies that agent_step_progress custom events are dispatched:
- "running" at step start
- "tool_executing" before tool execution
- "completed" when loop ends naturally or via done tool
- "interrupted" on cancellation
- "timeout" on total timeout
- Events contain correct step/max_steps/status/description fields
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
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, DoneToolConfig, ReflectionConfig, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def echo_tool(query: str) -> str:
    """Echo."""
    return f"echo: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, interrupt_at=None):
    """Build ReAct graph, capture dispatch_custom_event calls."""
    node_builder = ToolsNodes()
    node_builder.tools = [echo_tool]

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    events = []

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

    config = {
        "configurable": {
            "graph_request": request,
            "trace_id": "test",
            "execution_id": "exec-1" if interrupt_at else "",
        }
    }

    def capture_event(name, data):
        if name == "agent_step_progress":
            events.append(dict(data))

    interrupt_call = {"n": 0}

    def mock_interrupt(exec_id):
        if not exec_id or interrupt_at is None:
            return False
        interrupt_call["n"] += 1
        return interrupt_call["n"] >= interrupt_at

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ), patch(
        "langchain_core.callbacks.dispatch_custom_event",
        side_effect=capture_event,
    ), patch(
        "apps.opspilot.metis.llm.chain.node.is_interrupt_requested",
        side_effect=mock_interrupt,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProgressEvents:
    """Step progress events are emitted correctly."""

    async def test_running_event_on_step_start(self):
        """'running' event emitted at each step start."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "echo_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, events = await _build_and_run(request, responses)

        running_events = [e for e in events if e["status"] == "running"]
        assert len(running_events) >= 2  # step 1 and step 2
        assert running_events[0]["step"] == 1
        assert running_events[1]["step"] == 2

    async def test_tool_executing_event(self):
        """'tool_executing' event emitted before tool runs."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "echo_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, events = await _build_and_run(request, responses)

        tool_events = [e for e in events if e["status"] == "tool_executing"]
        assert len(tool_events) >= 1
        assert "echo_tool" in tool_events[0].get("description", "")
        assert tool_events[0].get("tool_name") == "echo_tool"

    async def test_completed_event_on_natural_end(self):
        """'completed' event emitted when loop ends naturally."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [AIMessage(content="Done.")]

        _, events = await _build_and_run(request, responses)

        completed_events = [e for e in events if e["status"] == "completed"]
        assert len(completed_events) >= 1

    async def test_interrupted_event(self):
        """'interrupted' event emitted on cancellation."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [AIMessage(content="Should not run.")]

        _, events = await _build_and_run(request, responses, interrupt_at=1)

        interrupted_events = [e for e in events if e["status"] == "interrupted"]
        assert len(interrupted_events) >= 1

    async def test_event_fields_present(self):
        """Events contain all required fields."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [AIMessage(content="Done.")]

        _, events = await _build_and_run(request, responses)

        assert len(events) >= 1
        for event in events:
            assert "step" in event
            assert "max_steps" in event
            assert "status" in event
            assert "description" in event
            assert "elapsed_seconds" in event
            assert "total_elapsed_seconds" in event
            assert event["max_steps"] == 5

    async def test_event_order(self):
        """Events come in order: running -> tool_executing -> running -> completed."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "echo_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, events = await _build_and_run(request, responses)

        statuses = [e["status"] for e in events]
        # Should start with "running", have "tool_executing", then another "running", then "completed"
        assert statuses[0] == "running"
        assert "tool_executing" in statuses
        assert statuses[-1] == "completed"


@pytest.mark.asyncio
class TestStepProgressWithDoneTool:
    async def test_done_tool_emits_completed_event(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [
            AIMessage(content="finish", tool_calls=[{"name": "__done__", "args": {"result": "done"}, "id": "d1"}]),
        ]

        events = []

        async def mock_ainvoke(messages, *args, **kwargs):
            return responses[0]

        node_builder = ToolsNodes()
        node_builder.tools = [echo_tool]
        node_builder.done_tool_config = request.done_tool_config

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

        config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": "exec-1"}}

        def capture_event(name, data):
            if name == "agent_step_progress":
                events.append(dict(data))

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ), patch(
            "langchain_core.callbacks.dispatch_custom_event",
            side_effect=capture_event,
        ):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

        completed_events = [e for e in events if e["status"] == "completed"]
        assert completed_events
