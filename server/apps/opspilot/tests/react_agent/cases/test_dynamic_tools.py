"""
Tests for dynamic tool switching in the ReAct agent loop.

Verifies that prepareStep hooks can:
- swap tool sets between steps
- phase in repair tools later
- choose tools from prior LLM output
- remove successful or failing tools
- add tools at runtime
- preserve earlier ToolMessages after tool-set changes
"""

# pyright: reportMissingImports=false

import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from typing import Annotated, TypedDict  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import (  # noqa: E402
    BasicLLMRequest,
    PrepareStepContext,
    PrepareStepResult,
    ReflectionConfig,
    RetryConfig,
    TimeoutConfig,
)
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402


@tool
def search_tool(query: str) -> str:
    """Search for information."""
    return f"search:{query}"


@tool
def calc_tool(expr: str) -> str:
    """Calculate a simple expression."""
    return f"calc:{expr}"


@tool
def diagnose_tool(query: str) -> str:
    """Diagnose a problem or raise on failures."""
    if "fail" in query.lower():
        raise RuntimeError("Error: diagnostic failed")
    return f"diagnostic:{query}"


@tool
def repair_tool(query: str) -> str:
    """Repair a problem."""
    return f"repair:{query}"


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _attach_prepare_step(request, hook):
    request.prepare_step_hooks = [hook]
    object.__setattr__(request, "prepare_step", hook)


async def _build_and_run(request, mock_llm_responses, tools_list=None):
    """Build the ReAct graph, run it, and capture LLM/tool binding data."""
    if tools_list is None:
        tools_list = [search_tool, calc_tool, diagnose_tool, repair_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    bound_tool_names_list = []

    async def mock_ainvoke(messages, *args, **kwargs):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    mock_llm = MagicMock()

    def track_bind(tools_arg, **kwargs):
        # Filter out auto-added tools (request_human_approval, request_user_choice)
        auto_tools = {"request_human_approval", "request_user_choice"}
        bound_tool_names_list.append([tool_item.name for tool_item in tools_arg if tool_item.name not in auto_tools])
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

    config: RunnableConfig = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": ""}}

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), call_count["n"], bound_tool_names_list


@pytest.mark.asyncio
class TestDynamicToolSwitch:
    async def test_switch_tools_between_steps(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number == 1:
                return PrepareStepResult(tools=[search_tool, calc_tool])
            if ctx.step_number == 2:
                return PrepareStepResult(tools=[diagnose_tool, repair_tool])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(
            request,
            responses,
            [search_tool, calc_tool, diagnose_tool, repair_tool],
        )

        assert llm_call_count == 2
        assert bound_tool_names[0] == ["search_tool", "calc_tool"]
        assert bound_tool_names[1] == ["diagnose_tool", "repair_tool"]

    async def test_phased_tool_strategy(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number <= 2:
                return PrepareStepResult(tools=[diagnose_tool])
            return PrepareStepResult(tools=[diagnose_tool, repair_tool])

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "diagnose_tool", "args": {"query": "phase-1"}, "id": "tc1"}]),
            AIMessage(content="", tool_calls=[{"name": "diagnose_tool", "args": {"query": "phase-2"}, "id": "tc2"}]),
            AIMessage(content="", tool_calls=[{"name": "repair_tool", "args": {"query": "phase-3"}, "id": "tc3"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [diagnose_tool, repair_tool])

        assert llm_call_count == 4
        assert bound_tool_names[0] == ["diagnose_tool"]
        assert bound_tool_names[1] == ["diagnose_tool"]
        assert bound_tool_names[2] == ["diagnose_tool", "repair_tool"]

    async def test_tool_selection_based_on_llm_output(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            last_ai = next((message for message in reversed(ctx.messages) if isinstance(message, AIMessage)), None)
            if last_ai is not None and "repair" in str(last_ai.content).lower():
                return PrepareStepResult(tools=[repair_tool])
            return PrepareStepResult(tools=[diagnose_tool])

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(
                content="repair required",
                tool_calls=[{"name": "diagnose_tool", "args": {"query": "test"}, "id": "tc1"}],
            ),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [diagnose_tool, repair_tool])

        assert llm_call_count == 2
        assert bound_tool_names[0] == ["diagnose_tool"]
        assert bound_tool_names[1] == ["repair_tool"]


@pytest.mark.asyncio
class TestDynamicToolRemoval:
    async def test_remove_completed_tool(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number >= 2:
                return PrepareStepResult(tools=[tool_item for tool_item in ctx.tools if tool_item.name != "search_tool"])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [search_tool, calc_tool])

        assert llm_call_count == 2
        # Note: auto-added tools are filtered out in track_bind
        assert bound_tool_names[0] == ["search_tool", "calc_tool"]
        assert bound_tool_names[1] == ["calc_tool"]

    async def test_remove_failing_tool(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            failures = [
                message
                for message in ctx.messages
                if isinstance(message, ToolMessage) and message.name == "diagnose_tool" and str(message.content).startswith("Error")
            ]
            if len(failures) >= 2:
                return PrepareStepResult(tools=[tool_item for tool_item in ctx.tools if tool_item.name != "diagnose_tool"])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "diagnose_tool", "args": {"query": "fail-1"}, "id": "tc1"}]),
            AIMessage(content="", tool_calls=[{"name": "diagnose_tool", "args": {"query": "fail-2"}, "id": "tc2"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [diagnose_tool, repair_tool])

        assert llm_call_count == 3
        # Note: auto-added tools are filtered out in track_bind
        assert bound_tool_names[0] == ["diagnose_tool", "repair_tool"]
        assert bound_tool_names[1] == ["diagnose_tool", "repair_tool"]
        assert bound_tool_names[2] == ["repair_tool"]


@pytest.mark.asyncio
class TestDynamicToolAddition:
    async def test_add_tool_at_runtime(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number == 2:
                return PrepareStepResult(tools=list(ctx.tools) + [repair_tool])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [search_tool])

        assert llm_call_count == 2
        # Note: auto-added tools (request_human_approval, request_user_choice) are filtered out in track_bind
        assert bound_tool_names[0] == ["search_tool"]
        assert "repair_tool" in bound_tool_names[1]

    async def test_added_tool_callable(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number == 2:
                return PrepareStepResult(tools=[search_tool, repair_tool])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}]),
            AIMessage(content="done"),
        ]

        _, llm_call_count, bound_tool_names = await _build_and_run(request, responses, [search_tool])

        assert llm_call_count == 2
        # Note: auto-added tools are filtered out; hook returns explicit tools list
        assert bound_tool_names[1] == ["search_tool", "repair_tool"]


@pytest.mark.asyncio
class TestToolSetIntegrity:
    async def test_previous_tool_results_preserved(self):
        async def hook(ctx: PrepareStepContext) -> PrepareStepResult:
            if ctx.step_number == 2:
                return PrepareStepResult(tools=[repair_tool])
            return PrepareStepResult()

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )
        _attach_prepare_step(request, hook)

        responses = [
            AIMessage(content="", tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}]),
            AIMessage(content="", tool_calls=[{"name": "repair_tool", "args": {"query": "test"}, "id": "tc2"}]),
            AIMessage(content="done"),
        ]

        messages, llm_call_count, bound_tool_names = await _build_and_run(
            request,
            responses,
            [search_tool, repair_tool],
        )

        assert llm_call_count == 3
        # Note: auto-added tools are filtered out in track_bind
        assert bound_tool_names[0] == ["search_tool", "repair_tool"]
        # When hook returns explicit tools list, only those tools are in the filtered list
        assert bound_tool_names[1] == ["repair_tool"]
        assert any(isinstance(message, ToolMessage) and message.name == "search_tool" for message in messages)
        assert any(isinstance(message, ToolMessage) and message.name == "repair_tool" for message in messages)
