"""
Tests for stopWhen flexible stop conditions in the ReAct agent loop.

Verifies that should_continue supports:
- max_steps: force-stop after N steps
- max_tokens_budget: force-stop when cumulative tokens exceed budget
- stop_when_conditions: custom condition chain
- Natural end when LLM returns no tool_calls

Tests run a real LangGraph ReAct loop with mock LLM and fake tools,
exercising the actual should_continue / agent_node / token_counter closures.
"""

import sys
import types

# Stub optional C-extension modules before Django imports
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, StopConditionContext, StopConditionResult  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Fake tool for testing
# ---------------------------------------------------------------------------


@tool
def fake_lookup(query: str) -> str:
    """Look up information."""
    return f"result for: {query}"


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper: build and run a minimal ReAct graph
# ---------------------------------------------------------------------------


async def _build_and_run(
    request: BasicLLMRequest,
    mock_llm_responses: list,
    tools=None,
):
    """Build a ReAct graph with mock LLM, execute, and return final messages + step count.

    Args:
        request: BasicLLMRequest with stopWhen config
        mock_llm_responses: list of AIMessage to return in sequence from LLM
        tools: list of tools (defaults to [fake_lookup])

    Returns:
        (final_messages, step_count) where step_count is how many times agent_node ran
    """
    if tools is None:
        tools = [fake_lookup]

    node_builder = ToolsNodes()
    node_builder.tools = tools

    # Track how many times LLM was called (= step count)
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

    entry_node = await node_builder.build_react_nodes(
        graph_builder=graph_builder,
        composite_node_name="test_react",
    )

    graph_builder.set_entry_point(entry_node)
    graph = graph_builder.compile()

    config = {
        "configurable": {
            "graph_request": request,
            "trace_id": "test",
        }
    }

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="test question")]},
        config=config,
    )

    return result.get("messages", []), call_count["n"]


def _make_tool_call_response(step: int, token_count: int = 0):
    """Create an AIMessage with a tool_call and optional usage_metadata."""
    msg = AIMessage(
        content=f"Let me look up step {step}",
        tool_calls=[{"name": "fake_lookup", "args": {"query": f"step{step}"}, "id": f"call_{step}"}],
    )
    if token_count > 0:
        msg.usage_metadata = {"total_tokens": token_count}
    return msg


def _make_final_response(content="Done."):
    """Create an AIMessage with no tool_calls (natural end)."""
    return AIMessage(content=content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStopWhenMaxSteps:
    """max_steps enforcement."""

    async def test_stops_at_max_steps(self):
        """Agent with max_steps=3 stops after 3 LLM calls even if LLM keeps requesting tools."""
        request = BasicLLMRequest(max_steps=3, compaction_enabled=False)
        # LLM always wants to call tools — never naturally stops
        infinite_tool_calls = [_make_tool_call_response(i) for i in range(10)]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, infinite_tool_calls)

        # Should have stopped at step 3 (not 10)
        assert steps == 3, f"Expected 3 steps, got {steps}"

    async def test_custom_max_steps(self):
        """max_steps=5 allows 5 steps."""
        request = BasicLLMRequest(max_steps=5, compaction_enabled=False)
        infinite_tool_calls = [_make_tool_call_response(i) for i in range(20)]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, infinite_tool_calls)

        assert steps == 5, f"Expected 5 steps, got {steps}"

    async def test_max_steps_zero_unlimited(self):
        """max_steps=0 means no step limit; LLM stops naturally."""
        request = BasicLLMRequest(max_steps=0, compaction_enabled=False)
        # 4 tool calls then natural end
        responses = [
            _make_tool_call_response(1),
            _make_tool_call_response(2),
            _make_tool_call_response(3),
            _make_tool_call_response(4),
            _make_final_response("All done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 5, f"Expected 5 steps (4 tool + 1 final), got {steps}"

    async def test_natural_end_before_max_steps(self):
        """LLM stops naturally at step 2, even though max_steps=10."""
        request = BasicLLMRequest(max_steps=10, compaction_enabled=False)
        responses = [
            _make_tool_call_response(1),
            _make_final_response("Done early."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Expected 2 steps, got {steps}"


@pytest.mark.asyncio
class TestStopWhenTokenBudget:
    """max_tokens_budget enforcement."""

    async def test_stops_when_budget_exceeded(self):
        """Token budget=1000, each step uses 600 tokens. Should stop after step 2 (1200 > 1000)."""
        request = BasicLLMRequest(
            max_steps=0,  # no step limit
            max_tokens_budget=1000,
            compaction_enabled=False,
        )
        responses = [
            _make_tool_call_response(1, token_count=600),
            _make_tool_call_response(2, token_count=600),  # cumulative 1200 > 1000
            _make_tool_call_response(3, token_count=600),
            _make_final_response("Should not reach here."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        # Step 1: 600 tokens -> continue; Step 2: 1200 tokens -> should_continue says end
        assert steps == 2, f"Expected 2 steps, got {steps}"

    async def test_budget_zero_unlimited(self):
        """max_tokens_budget=0 means no budget limit."""
        request = BasicLLMRequest(
            max_steps=0,
            max_tokens_budget=0,
            compaction_enabled=False,
        )
        responses = [
            _make_tool_call_response(1, token_count=50000),
            _make_tool_call_response(2, token_count=50000),
            _make_final_response("Done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 3, f"Expected 3 steps (budget unlimited), got {steps}"

    async def test_no_usage_metadata_does_not_trigger(self):
        """LLM returns no usage_metadata — token counter stays 0, budget not triggered."""
        request = BasicLLMRequest(
            max_steps=0,
            max_tokens_budget=100,
            compaction_enabled=False,
        )
        # token_count=0 means no usage_metadata set
        responses = [
            _make_tool_call_response(1, token_count=0),
            _make_tool_call_response(2, token_count=0),
            _make_final_response("Done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 3, f"Expected 3 steps (no usage_metadata, budget not triggered), got {steps}"


@pytest.mark.asyncio
class TestStopWhenCustomConditions:
    """Custom stop_when_conditions."""

    async def test_custom_condition_triggers_stop(self):
        """Custom condition: stop when step >= 2."""

        def stop_at_step_2(ctx: StopConditionContext) -> StopConditionResult:
            if ctx.step_number >= 2:
                return StopConditionResult(should_stop=True, reason="Reached step 2")
            return StopConditionResult(should_stop=False)

        request = BasicLLMRequest(
            max_steps=0,
            compaction_enabled=False,
            stop_when_conditions=[stop_at_step_2],
        )
        responses = [_make_tool_call_response(i) for i in range(10)]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Expected 2 steps (custom condition), got {steps}"

    async def test_custom_condition_does_not_trigger(self):
        """Condition always returns should_stop=False — loop continues normally."""

        def never_stop(ctx: StopConditionContext) -> StopConditionResult:
            return StopConditionResult(should_stop=False)

        request = BasicLLMRequest(
            max_steps=0,
            compaction_enabled=False,
            stop_when_conditions=[never_stop],
        )
        responses = [
            _make_tool_call_response(1),
            _make_final_response("Done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Expected 2 steps (natural end), got {steps}"

    async def test_multiple_conditions_first_triggers(self):
        """Two conditions: A never stops, B stops at step 3. B should trigger."""

        def never_stop(ctx: StopConditionContext) -> StopConditionResult:
            return StopConditionResult(should_stop=False)

        def stop_at_3(ctx: StopConditionContext) -> StopConditionResult:
            if ctx.step_number >= 3:
                return StopConditionResult(should_stop=True, reason="Step 3 reached")
            return StopConditionResult(should_stop=False)

        request = BasicLLMRequest(
            max_steps=0,
            compaction_enabled=False,
            stop_when_conditions=[never_stop, stop_at_3],
        )
        responses = [_make_tool_call_response(i) for i in range(10)]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 3, f"Expected 3 steps (condition B triggers), got {steps}"

    async def test_condition_exception_does_not_break_loop(self):
        """Condition raises exception — loop continues as if condition didn't exist."""

        def broken_condition(ctx: StopConditionContext) -> StopConditionResult:
            raise RuntimeError("Condition exploded")

        request = BasicLLMRequest(
            max_steps=0,
            compaction_enabled=False,
            stop_when_conditions=[broken_condition],
        )
        responses = [
            _make_tool_call_response(1),
            _make_final_response("Done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Expected 2 steps (exception ignored), got {steps}"

    async def test_condition_receives_correct_context(self):
        """Verify StopConditionContext fields are populated correctly."""
        captured_contexts = []

        def capture_condition(ctx: StopConditionContext) -> StopConditionResult:
            captured_contexts.append(ctx.model_copy())
            return StopConditionResult(should_stop=False)

        request = BasicLLMRequest(
            max_steps=0,
            compaction_enabled=False,
            stop_when_conditions=[capture_condition],
        )
        responses = [
            _make_tool_call_response(1, token_count=100),
            _make_tool_call_response(2, token_count=200),
            _make_final_response("Done."),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            await _build_and_run(request, responses)

        # should_continue is called after agent_node, so conditions see step 1 and 2
        assert len(captured_contexts) == 2, f"Expected 2 condition calls, got {len(captured_contexts)}"

        # First call: step 1, 100 tokens
        assert captured_contexts[0].step_number == 1
        assert captured_contexts[0].total_tokens == 100
        assert len(captured_contexts[0].last_tool_calls) == 1
        assert captured_contexts[0].last_tool_calls[0]["name"] == "fake_lookup"

        # Second call: step 2, 300 cumulative tokens
        assert captured_contexts[1].step_number == 2
        assert captured_contexts[1].total_tokens == 300


@pytest.mark.asyncio
class TestStopWhenNaturalEnd:
    """Natural termination (no tool_calls)."""

    async def test_no_tool_calls_ends_immediately(self):
        """LLM returns plain text on first call — single step, no tools."""
        request = BasicLLMRequest(max_steps=50, compaction_enabled=False)
        responses = [_make_final_response("I can answer directly.")]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 1

    async def test_empty_messages_ends(self):
        """Edge case: if state has no messages, should_continue returns end."""
        # This is implicitly tested — if agent_node returns empty messages,
        # should_continue sees no last_message and ends.
        request = BasicLLMRequest(max_steps=50, compaction_enabled=False)

        # Mock LLM returns None -> agent_node returns {"messages": []}
        async def mock_ainvoke(messages, *args, **kwargs):
            return None

        node_builder = ToolsNodes()
        node_builder.tools = [fake_lookup]

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

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config={"configurable": {"graph_request": request, "trace_id": "test"}},
            )

        # Should not crash, just end gracefully
        assert "messages" in result


@pytest.mark.asyncio
class TestStopWhenCombined:
    """Combining multiple stop mechanisms."""

    async def test_token_budget_before_max_steps(self):
        """Token budget triggers before max_steps is reached."""
        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=500,
            compaction_enabled=False,
        )
        responses = [
            _make_tool_call_response(1, token_count=300),
            _make_tool_call_response(2, token_count=300),  # cumulative 600 > 500
            _make_tool_call_response(3, token_count=300),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Token budget should trigger at step 2, got {steps}"

    async def test_max_steps_before_token_budget(self):
        """Max steps triggers before token budget."""
        request = BasicLLMRequest(
            max_steps=2,
            max_tokens_budget=100000,
            compaction_enabled=False,
        )
        responses = [
            _make_tool_call_response(1, token_count=100),
            _make_tool_call_response(2, token_count=100),
            _make_tool_call_response(3, token_count=100),
        ]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        assert steps == 2, f"Max steps should trigger at step 2, got {steps}"

    async def test_custom_condition_overrides_both(self):
        """Custom condition stops at step 1, even though max_steps=10 and budget is huge."""

        def stop_immediately(ctx: StopConditionContext) -> StopConditionResult:
            return StopConditionResult(should_stop=True, reason="Stop now")

        request = BasicLLMRequest(
            max_steps=10,
            max_tokens_budget=100000,
            compaction_enabled=False,
            stop_when_conditions=[stop_immediately],
        )
        responses = [_make_tool_call_response(i) for i in range(10)]

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            messages, steps = await _build_and_run(request, responses)

        # Step 1 runs, then should_continue checks: max_steps not hit (1<10),
        # budget not hit, but custom condition says stop
        assert steps == 1, f"Custom condition should stop at step 1, got {steps}"
