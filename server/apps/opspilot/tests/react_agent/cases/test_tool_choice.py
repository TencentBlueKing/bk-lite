"""
Tests for #5 toolChoice 控制.

Verifies:
- mode="auto": no tool_choice kwarg passed to bind_tools
- mode="none": tool_choice="none" passed
- mode="any": tool_choice="any" passed
- mode="specific": tool_choice=<tool_name> passed
- apply_on_steps: only applies on specified steps
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig, TimeoutConfig, ToolChoiceConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def search_tool(query: str) -> str:
    """Search."""
    return f"found: {query}"


@tool
def calc_tool(expr: str) -> str:
    """Calculate."""
    return f"result: {expr}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools_list=None):
    """Build ReAct graph, track bind_tools kwargs per call."""
    if tools_list is None:
        tools_list = [search_tool, calc_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    bind_kwargs_list = []

    async def mock_ainvoke(messages, *args, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    mock_llm = MagicMock()

    def track_bind(tools_arg, **kwargs):
        bind_kwargs_list.append(dict(kwargs))
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

    return result.get("messages", []), bind_kwargs_list


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolChoiceAuto:
    """mode=auto (default) — no tool_choice kwarg."""

    async def test_auto_no_tool_choice_kwarg(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="auto"),
        )
        responses = [AIMessage(content="Done.")]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert len(bind_kwargs) >= 1
        assert "tool_choice" not in bind_kwargs[0]

    async def test_default_config_is_auto(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(),
        )
        responses = [AIMessage(content="Done.")]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert len(bind_kwargs) >= 1
        assert "tool_choice" not in bind_kwargs[0]


@pytest.mark.asyncio
class TestToolChoiceNone:
    """mode=none — tool_choice='none' passed."""

    async def test_none_mode(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="none"),
        )
        responses = [AIMessage(content="Done.")]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "none"

    async def test_none_mode_llm_outputs_text(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="none"),
        )
        responses = [AIMessage(content="text answer")]

        messages, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "none"
        assert messages[-1].content == "text answer"


@pytest.mark.asyncio
class TestToolChoiceAny:
    """mode=any — tool_choice='any' passed."""

    async def test_any_mode(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="any"),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "any"

    async def test_anthropic_compatible_thinking_downgrades_any_to_auto(self):
        request = BasicLLMRequest(
            protocol_type="anthropic",
            vendor_type="deepseek",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="any"),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "auto"

    async def test_any_mode_forces_tool_use(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="any"),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "calc_tool", "args": {"expr": "1+1"}, "id": "c2"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "any"
        assert bind_kwargs[1]["tool_choice"] == "any"


@pytest.mark.asyncio
class TestToolChoiceSpecific:
    """mode=specific — tool_choice=<name> passed."""

    async def test_specific_mode(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="specific", tool_name="calc_tool"),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "calc_tool", "args": {"expr": "1+1"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0]["tool_choice"] == "calc_tool"

    async def test_specific_empty_name_fallback_auto(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="specific", tool_name=""),
        )
        responses = [AIMessage(content="Done.")]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert "tool_choice" not in bind_kwargs[0]


@pytest.mark.asyncio
class TestToolChoiceApplyOnSteps:
    """apply_on_steps limits which steps get tool_choice."""

    async def test_only_applies_on_specified_steps(self):
        """tool_choice applied only on step 1, not step 2."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="any", apply_on_steps=[1]),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        # Step 1: tool_choice applied
        assert bind_kwargs[0].get("tool_choice") == "any"
        # Step 2: not in apply_on_steps, so no tool_choice
        if len(bind_kwargs) >= 2:
            assert "tool_choice" not in bind_kwargs[1]

    async def test_not_applied_on_unlisted_step(self):
        """tool_choice only on step 2 — step 1 has no constraint."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="none", apply_on_steps=[2]),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        # Step 1: not in apply_on_steps
        assert "tool_choice" not in bind_kwargs[0]
        # Step 2: in apply_on_steps
        if len(bind_kwargs) >= 2:
            assert bind_kwargs[1].get("tool_choice") == "none"

    async def test_apply_on_all_steps_when_none(self):
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            tool_choice_config=ToolChoiceConfig(mode="any", apply_on_steps=None),
        )
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        _, bind_kwargs = await _build_and_run(request, responses)

        assert bind_kwargs[0].get("tool_choice") == "any"
        assert bind_kwargs[1].get("tool_choice") == "any"
