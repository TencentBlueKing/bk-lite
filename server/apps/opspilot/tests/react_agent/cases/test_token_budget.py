"""
Tests for token budget graceful termination.

Verifies the two-tier budget system:
1. Soft budget (default 80%): injects wrap-up prompt to nudge LLM to conclude
2. Hard budget (100%): forces loop termination via should_continue

Key behaviors:
- Below soft threshold: no wrap-up prompt
- Between soft and hard: wrap-up prompt injected each step
- At/above hard budget: loop terminates immediately
- soft_budget_ratio=1.0 disables soft budget
- max_tokens_budget=0 disables both
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def dummy_tool(query: str) -> str:
    """A simple tool."""
    return f"ok: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, usage_per_call=None):
    """Build ReAct graph, run with mock LLM that reports usage_metadata.

    Args:
        usage_per_call: list of total_tokens values per LLM call, or int for constant.
    """
    node_builder = ToolsNodes()
    node_builder.tools = [dummy_tool]

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    llm_inputs = []

    if usage_per_call is None:
        usage_per_call = [100] * len(responses)
    elif isinstance(usage_per_call, int):
        usage_per_call = [usage_per_call] * len(responses)

    async def mock_ainvoke(messages, *args, **kwargs):
        llm_inputs.append(list(messages))
        idx = min(call_count["n"], len(responses) - 1)
        resp = responses[idx]
        # Attach usage_metadata
        usage_idx = min(call_count["n"], len(usage_per_call) - 1)
        resp.usage_metadata = {"total_tokens": usage_per_call[usage_idx]}
        call_count["n"] += 1
        return resp

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

    def mock_render(template, ctx):
        if "budget_wrapup" in template:
            return f"[WRAPUP: {ctx.get('used_percent', 0)}% used, {ctx.get('used_tokens', 0)}/{ctx.get('total_budget', 0)}]"
        return "You are a test assistant."

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        side_effect=mock_render,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), llm_inputs


# ---------------------------------------------------------------------------
# Tests: Soft Budget (wrap-up prompt injection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBudgetSoftThreshold:
    """Soft budget threshold injects wrap-up prompt."""

    async def test_wrapup_injected_when_above_soft(self):
        """When tokens exceed soft threshold (80%), wrap-up prompt is injected."""
        # Budget=1000, soft=80% -> threshold at 800
        # Step 1 uses 500 tokens (below soft), step 2 uses 400 tokens (total=900, above soft)
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "dummy_tool", "args": {"query": "b"}, "id": "c2"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[500, 400, 200])

        # Step 1: token_counter=0 before check (usage added after LLM call), no wrapup
        # Step 2: token_counter=500, still below 800, no wrapup
        # Step 3: token_counter=900, above 800 and below 1000 -> wrapup injected
        third_call = llm_inputs[2]
        contents = [str(getattr(m, "content", "")) for m in third_call]
        assert any("[WRAPUP:" in c for c in contents), f"Expected wrap-up prompt in 3rd call, got: {contents}"

    async def test_no_wrapup_below_soft(self):
        """When tokens are below soft threshold, no wrap-up."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=10000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[100, 100])

        # Total is only 200 which is way below 8000 (80% of 10000)
        for call_msgs in llm_inputs:
            contents = [str(getattr(m, "content", "")) for m in call_msgs]
            assert not any("[WRAPUP:" in c for c in contents)

    async def test_soft_disabled_with_ratio_1(self):
        """soft_budget_ratio=1.0 disables soft budget (only hard limit applies)."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=1.0,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[900, 50])

        # Even at 900/1000 (90%), no wrapup because ratio=1.0
        for call_msgs in llm_inputs:
            contents = [str(getattr(m, "content", "")) for m in call_msgs]
            assert not any("[WRAPUP:" in c for c in contents)


# ---------------------------------------------------------------------------
# Tests: Hard Budget (forced termination)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBudgetHardLimit:
    """Hard budget terminates the loop."""

    async def test_terminates_at_hard_budget(self):
        """When tokens >= max_tokens_budget, loop stops."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=500,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            # After step 1, token_counter=600 >= 500, should_continue returns "end"
            AIMessage(content="Should not be called."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[600, 100])

        # Only 1 LLM call — loop terminated after first response exceeded budget
        assert len(llm_inputs) == 1

    async def test_no_termination_when_budget_zero(self):
        """max_tokens_budget=0 means unlimited — no termination."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=0,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "dummy_tool", "args": {"query": "b"}, "id": "c2"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[50000, 50000, 50000])

        # All 3 calls made — budget=0 doesn't limit
        assert len(llm_inputs) == 3


# ---------------------------------------------------------------------------
# Tests: Combined soft + hard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenBudgetCombined:
    """Soft and hard budget work together."""

    async def test_wrapup_then_hard_stop(self):
        """Soft triggers wrapup first, then hard stops if LLM keeps going."""
        # Budget=1000, soft at 80% = 800
        # Step 1: 500 tokens -> total=500 (below soft)
        # Step 2: 400 tokens -> total=900 (above soft, below hard) -> wrapup on step 3
        # Step 3: 200 tokens -> total=1100 (above hard) -> should_continue stops
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "dummy_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "dummy_tool", "args": {"query": "b"}, "id": "c2"}]),
            AIMessage(content="t3", tool_calls=[{"name": "dummy_tool", "args": {"query": "c"}, "id": "c3"}]),
            AIMessage(content="Should not reach."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, usage_per_call=[500, 400, 200, 100])

        # Step 3 should have wrapup injected
        if len(llm_inputs) >= 3:
            third_call = llm_inputs[2]
            contents = [str(getattr(m, "content", "")) for m in third_call]
            assert any("[WRAPUP:" in c for c in contents)

        # After step 3, total=1100 >= 1000 -> hard stop, so max 3 LLM calls
        assert len(llm_inputs) == 3
