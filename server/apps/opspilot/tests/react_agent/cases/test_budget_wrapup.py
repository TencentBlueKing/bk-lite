"""
Tests for token budget graceful termination (Phase 2 #12).

Verifies that when cumulative tokens approach the budget:
- Soft threshold (default 80%) injects a wrap-up prompt
- Hard threshold (100%) still force-stops via should_continue
- soft_budget_ratio=1.0 disables the wrap-up injection
- Wrap-up prompt only injected once (not repeated every step)
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def lookup(query: str) -> str:
    """Look up information."""
    return f"result: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools=None):
    """Build ReAct graph, run with mock LLM, return (messages, llm_call_inputs)."""
    if tools is None:
        tools = [lookup]

    node_builder = ToolsNodes()
    node_builder.tools = tools

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

    config = {"configurable": {"graph_request": request, "trace_id": "test"}}

    def _mock_render(template, ctx):
        if "budget_wrapup" in template:
            return f"[WRAPUP: {ctx.get('used_percent', 0)}% used]"
        if "reflection" in template:
            return f"[REFLECTION: {ctx.get('reason', '')}]"
        return "You are a test assistant."

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        side_effect=_mock_render,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), llm_inputs


def _make_tool_call_response(step: int, token_count: int = 0):
    msg = AIMessage(
        content=f"Step {step}",
        tool_calls=[{"name": "lookup", "args": {"query": f"step{step}"}, "id": f"call_{step}"}],
    )
    if token_count > 0:
        msg.usage_metadata = {"total_tokens": token_count}
    return msg


def _make_final_response(content="Done."):
    return AIMessage(content=content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBudgetWrapup:
    """Soft budget threshold injects wrap-up prompt."""

    async def test_wrapup_injected_at_soft_threshold(self):
        """Budget=1000, soft=0.8. Step1 uses 850 tokens (85% > 80%). Step 2 should see wrap-up."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=850),  # 85% > 80% soft threshold
            _make_final_response("Wrapping up with answer."),  # agent wraps up
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        # Second LLM call should contain wrap-up prompt
        assert len(llm_inputs) >= 2
        second_call = llm_inputs[1]
        wrapup_found = any("[WRAPUP:" in str(getattr(m, "content", "")) for m in second_call)
        assert wrapup_found, f"Expected wrap-up prompt in 2nd LLM call, got: " f"{[str(getattr(m, 'content', ''))[:60] for m in second_call]}"

    async def test_no_wrapup_below_soft_threshold(self):
        """Budget=1000, soft=0.8. Step1 uses 500 tokens (50% < 80%). No wrap-up."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=500),  # 50% < 80%
            _make_final_response("Done normally."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[WRAPUP:" not in str(getattr(m, "content", ""))

    async def test_wrapup_disabled_with_ratio_1(self):
        """soft_budget_ratio=1.0 disables wrap-up (only hard stop at 100%)."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=1.0,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=900),  # 90% but ratio=1.0
            _make_tool_call_response(2, token_count=200),  # 110% -> hard stop
            _make_final_response("Should not reach."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        # No wrap-up prompt anywhere
        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[WRAPUP:" not in str(getattr(m, "content", ""))

    async def test_hard_stop_still_works_after_wrapup(self):
        """Even after wrap-up injection, hard stop at 100% still terminates."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=850),  # 85% -> wrap-up on step 2
            _make_tool_call_response(2, token_count=200),  # 1050 > 1000 -> hard stop
            _make_tool_call_response(3, token_count=100),  # should not run
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        # Step 2 ran (with wrap-up), step 3 should NOT have run due to hard stop
        assert len(llm_inputs) == 2, f"Expected 2 LLM calls (hard stop after step 2), got {len(llm_inputs)}"

    async def test_no_wrapup_when_budget_zero(self):
        """Budget=0 means unlimited, no wrap-up ever."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=0,
            soft_budget_ratio=0.8,
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=99999),
            _make_final_response("Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[WRAPUP:" not in str(getattr(m, "content", ""))

    async def test_wrapup_not_repeated(self):
        """Wrap-up injected on step 2, but if agent continues (still under hard limit), step 3 also gets it.
        This is acceptable — each step that's over soft threshold gets the reminder."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=1000,
            soft_budget_ratio=0.5,  # 50% threshold
            compaction_enabled=False,
            reflection_config={"enabled": False},
        )
        responses = [
            _make_tool_call_response(1, token_count=600),  # 60% > 50%, wrap-up on step 2
            _make_tool_call_response(2, token_count=100),  # 70% > 50%, wrap-up on step 3 too
            _make_final_response("Done."),  # 70% still < 100%, natural end
        ]

        messages, llm_inputs = await _build_and_run(request, responses)

        # Both step 2 and step 3 should have wrap-up (persistent reminder)
        wrapup_count = 0
        for call_msgs in llm_inputs:
            if any("[WRAPUP:" in str(getattr(m, "content", "")) for m in call_msgs):
                wrapup_count += 1
        assert wrapup_count >= 2, f"Expected wrap-up in steps 2+3, got {wrapup_count} occurrences"
