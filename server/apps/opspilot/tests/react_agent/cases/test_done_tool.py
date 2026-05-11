"""
Tests for #7 done tool 显式终止.

Verifies:
- Done tool is added to available tools when enabled
- LLM calling done tool terminates loop immediately
- Done tool result is returned as final AIMessage content
- JSON parsing of done tool result (valid/invalid)
- Done tool disabled — not added to tools
- Other tool calls in same response are ignored when done tool present
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
def search_tool(query: str) -> str:
    """Search for info."""
    return f"found: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools_list=None):
    """Build ReAct graph, run with mock LLM, return (messages, llm_calls, bound_tool_names)."""
    if tools_list is None:
        tools_list = [search_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools_list
    node_builder.done_tool_config = request.done_tool_config

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    bound_tool_names_list = []

    async def mock_ainvoke(messages, *args, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    mock_llm = MagicMock()

    def track_bind(tools_arg, **kwargs):
        bound_tool_names_list.append([getattr(t, "name", str(t)) for t in tools_arg])
        bound = MagicMock()
        bound.ainvoke = mock_ainvoke
        return bound

    mock_llm.bind_tools = track_bind
    node_builder.get_llm_client = lambda *a, **kw: mock_llm

    graph_builder = StateGraph(AgentState)
    entry = await node_builder.build_react_nodes(
        graph_builder=graph_builder,
        composite_node_name="test_react",
    )
    graph_builder.set_entry_point(entry)
    graph = graph_builder.compile()

    config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": ""}}

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), call_count["n"], bound_tool_names_list


# ---------------------------------------------------------------------------
# Tests: Done tool enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDoneToolEnabled:
    """Done tool behavior when enabled."""

    async def test_done_tool_added_to_bound_tools(self):
        """When enabled, done tool appears in LLM's bound tools."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [AIMessage(content="Just answering.")]

        messages, llm_calls, bound_names = await _build_and_run(request, responses)

        assert len(bound_names) >= 1
        assert "__done__" in bound_names[0]
        assert "search_tool" in bound_names[0]

    async def test_done_tool_terminates_loop(self):
        """LLM calling done tool ends loop immediately — no tool_node execution."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [
            AIMessage(
                content="I have the answer.",
                tool_calls=[{"name": "__done__", "args": {"result": '{"answer": "42"}'}, "id": "done_1"}],
            ),
            AIMessage(content="Should not be called."),
        ]

        messages, llm_calls, _ = await _build_and_run(request, responses)

        # Only 1 LLM call — done tool intercepted immediately
        assert llm_calls == 1
        # Final message contains the structured result
        last_content = str(getattr(messages[-1], "content", ""))
        assert "42" in last_content

    async def test_done_tool_json_result_parsed(self):
        """Valid JSON result is parsed and returned."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        json_result = '{"status": "success", "data": [1, 2, 3]}'
        responses = [
            AIMessage(
                content="Done",
                tool_calls=[{"name": "__done__", "args": {"result": json_result}, "id": "d1"}],
            ),
        ]

        messages, _, _ = await _build_and_run(request, responses)

        last_content = str(getattr(messages[-1], "content", ""))
        assert "success" in last_content
        assert "[1, 2, 3]" in last_content

    async def test_done_tool_invalid_json_returned_as_string(self):
        """Invalid JSON in result is returned as-is string."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [
            AIMessage(
                content="Done",
                tool_calls=[{"name": "__done__", "args": {"result": "plain text answer"}, "id": "d1"}],
            ),
        ]

        messages, _, _ = await _build_and_run(request, responses)

        last_content = str(getattr(messages[-1], "content", ""))
        assert "plain text answer" in last_content

    async def test_done_tool_with_other_tool_calls(self):
        """If done tool is among multiple tool_calls, done tool takes priority."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [
            AIMessage(
                content="Finishing",
                tool_calls=[
                    {"name": "search_tool", "args": {"query": "x"}, "id": "c1"},
                    {"name": "__done__", "args": {"result": '{"final": true}'}, "id": "d1"},
                ],
            ),
        ]

        messages, llm_calls, _ = await _build_and_run(request, responses)

        # Done tool intercepted — only 1 call, no tool execution
        assert llm_calls == 1
        last_content = str(getattr(messages[-1], "content", ""))
        assert "final" in last_content

    async def test_done_tool_after_normal_steps(self):
        """Agent does work first, then calls done tool to finish."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="__done__"),
        )

        responses = [
            AIMessage(content="searching", tool_calls=[{"name": "search_tool", "args": {"query": "info"}, "id": "c1"}]),
            AIMessage(
                content="Got it",
                tool_calls=[{"name": "__done__", "args": {"result": '{"answer": "found info"}'}, "id": "d1"}],
            ),
        ]

        messages, llm_calls, _ = await _build_and_run(request, responses)

        # 2 LLM calls: first does search, second calls done
        assert llm_calls == 2
        last_content = str(getattr(messages[-1], "content", ""))
        assert "found info" in last_content


# ---------------------------------------------------------------------------
# Tests: Done tool disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDoneToolDisabled:
    """Done tool not added when disabled."""

    async def test_disabled_not_in_tools(self):
        """When disabled, done tool is NOT in bound tools."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=False),
        )

        responses = [AIMessage(content="Done.")]

        messages, _, bound_names = await _build_and_run(request, responses)

        assert len(bound_names) >= 1
        assert "__done__" not in bound_names[0]


# ---------------------------------------------------------------------------
# Tests: Custom done tool name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDoneToolCustomName:
    """Custom tool_name works."""

    async def test_custom_name_intercepted(self):
        """Custom done tool name is recognized and intercepted."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            done_tool_config=DoneToolConfig(enabled=True, tool_name="finish_task"),
        )

        responses = [
            AIMessage(
                content="Finishing",
                tool_calls=[{"name": "finish_task", "args": {"result": '{"done": true}'}, "id": "f1"}],
            ),
        ]

        messages, llm_calls, bound_names = await _build_and_run(request, responses)

        assert llm_calls == 1
        assert "finish_task" in bound_names[0]
        last_content = str(getattr(messages[-1], "content", ""))
        assert "done" in last_content
