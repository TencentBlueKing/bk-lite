"""
Tests for prepareStep hooks in the ReAct agent loop.

Verifies that before each LLM call, registered hooks can:
- Inspect step context (step_number, messages, tools, model)
- Modify messages for the upcoming LLM call
- Modify the active tool set
- Override additional system prompt
- Force-stop the loop early
- Handle async hooks
- Tolerate hook exceptions without breaking the loop
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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, PrepareStepContext, PrepareStepResult, ReflectionConfig, RetryConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def search_tool(query: str) -> str:
    """Search for information."""
    return f"found: {query}"


@tool
def calc_tool(expr: str) -> str:
    """Calculate expression."""
    return f"result: {expr}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools_list):
    """Build ReAct graph, run with mock LLM, return (messages, llm_call_inputs)."""
    node_builder = ToolsNodes()
    node_builder.tools = tools_list

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

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), llm_inputs


# ---------------------------------------------------------------------------
# Tests: Basic Hook Invocation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepBasic:
    """Basic hook invocation and context."""

    async def test_hook_receives_correct_context(self):
        """Hook receives step_number, messages, tools, and model."""
        captured_contexts = []

        def capture_hook(ctx: PrepareStepContext):
            captured_contexts.append(
                {
                    "step": ctx.step_number,
                    "msg_count": len(ctx.messages),
                    "tool_count": len(ctx.tools),
                    "model": ctx.model,
                }
            )
            return None  # no modification

        request = BasicLLMRequest(
            model="gpt-4o",
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[capture_hook],
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        await _build_and_run(request, responses, [search_tool])

        assert len(captured_contexts) == 2  # called before each LLM invocation
        assert captured_contexts[0]["step"] == 1
        assert captured_contexts[0]["model"] == "gpt-4o"
        assert captured_contexts[0]["tool_count"] == 3  # search_tool + request_human_approval + request_user_choice
        assert captured_contexts[1]["step"] == 2
        # After tool execution, messages grew
        assert captured_contexts[1]["msg_count"] > captured_contexts[0]["msg_count"]

    async def test_hook_not_called_when_empty(self):
        """No hooks registered — no errors, normal execution."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[],
        )

        responses = [AIMessage(content="Done.")]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])
        assert len(llm_inputs) == 1

    async def test_step_number_increments(self):
        """step_number increments across multiple tool-call rounds."""
        captured_steps = []

        def capture_hook(ctx: PrepareStepContext):
            captured_steps.append(ctx.step_number)
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[capture_hook],
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "search_tool", "args": {"query": "y"}, "id": "c2"}]),
            AIMessage(content="Done."),
        ]

        await _build_and_run(request, responses, [search_tool])

        assert captured_steps == [1, 2, 3]


# ---------------------------------------------------------------------------
# Tests: Modifying Messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepModifyMessages:
    """Hook modifies messages before LLM call."""

    async def test_inject_extra_message(self):
        """Hook appends a message — LLM sees it."""

        def inject_hook(ctx: PrepareStepContext):
            if ctx.step_number == 1:
                new_msgs = list(ctx.messages) + [HumanMessage(content="[INJECTED]")]
                return PrepareStepResult(messages=new_msgs)
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[inject_hook],
        )

        responses = [AIMessage(content="Got it.")]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])

        # First LLM call should contain injected message
        first_call = llm_inputs[0]
        contents = [str(getattr(m, "content", "")) for m in first_call]
        assert any("[INJECTED]" in c for c in contents)


# ---------------------------------------------------------------------------
# Tests: Modifying Tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepModifyTools:
    """Hook modifies available tools."""

    async def test_replace_tools(self):
        """Hook replaces tool set — LLM is bound with new tools."""
        bind_calls = []

        def replace_tools_hook(ctx: PrepareStepContext):
            # On step 1, restrict to only calc_tool
            if ctx.step_number == 1:
                return PrepareStepResult(tools=[calc_tool])
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[replace_tools_hook],
        )

        responses = [AIMessage(content="Done.")]

        # We need to track what tools are bound
        node_builder = ToolsNodes()
        node_builder.tools = [search_tool, calc_tool]

        call_count = {"n": 0}

        async def mock_ainvoke(messages, *args, **kwargs):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        mock_llm = MagicMock()

        def track_bind_tools(tools_arg, **kwargs):
            bind_calls.append([getattr(t, "name", str(t)) for t in tools_arg])
            bound = MagicMock()
            bound.ainvoke = mock_ainvoke
            return bound

        mock_llm.bind_tools = track_bind_tools
        node_builder.get_llm_client = lambda *a, **kw: mock_llm

        graph_builder = StateGraph(AgentState)
        entry = await node_builder.build_react_nodes(
            graph_builder=graph_builder,
            composite_node_name="test_react",
        )
        graph_builder.set_entry_point(entry)
        graph = graph_builder.compile()

        config = {"configurable": {"graph_request": request, "trace_id": "test"}}

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

        # Should have bound with only calc_tool
        assert len(bind_calls) >= 1
        assert bind_calls[0] == ["calc_tool"]

    async def test_add_new_tool(self):
        """Hook adds a new tool on step 2."""
        bind_calls = []

        def add_tool_hook(ctx: PrepareStepContext):
            if ctx.step_number == 1:
                return PrepareStepResult(tools=[search_tool])
            if ctx.step_number == 2:
                return PrepareStepResult(tools=[search_tool, calc_tool])
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[add_tool_hook],
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "calc_tool", "args": {"expr": "1+1"}, "id": "c2"}]),
            AIMessage(content="Done."),
        ]

        node_builder = ToolsNodes()
        node_builder.tools = [search_tool, calc_tool]

        call_count = {"n": 0}

        async def mock_ainvoke(messages, *args, **kwargs):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        mock_llm = MagicMock()

        def track_bind_tools(tools_arg, **kwargs):
            bind_calls.append([getattr(t, "name", str(t)) for t in tools_arg])
            bound = MagicMock()
            bound.ainvoke = mock_ainvoke
            return bound

        mock_llm.bind_tools = track_bind_tools
        node_builder.get_llm_client = lambda *a, **kw: mock_llm

        graph_builder = StateGraph(AgentState)
        entry = await node_builder.build_react_nodes(
            graph_builder=graph_builder,
            composite_node_name="test_react",
        )
        graph_builder.set_entry_point(entry)
        graph = graph_builder.compile()

        config = {"configurable": {"graph_request": request, "trace_id": "test"}}

        with patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

        assert len(bind_calls) >= 2
        assert "search_tool" in bind_calls[0]
        assert "calc_tool" in bind_calls[1]


# ---------------------------------------------------------------------------
# Tests: Force Stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepForceStop:
    """Hook can force-stop the agent loop."""

    async def test_stop_on_step_2(self):
        """Hook stops loop at step 2 — LLM not called for step 2."""

        def stop_hook(ctx: PrepareStepContext):
            if ctx.step_number >= 2:
                return PrepareStepResult(stop=True, metadata={"stop_message": "Budget exceeded"})
            return None

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[stop_hook],
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "search_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Should not reach here."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])

        # LLM called only once (step 1), step 2 was stopped by hook
        assert len(llm_inputs) == 1
        # Final message should contain stop message
        last_content = str(getattr(messages[-1], "content", ""))
        assert "Budget exceeded" in last_content

    async def test_stop_on_step_1(self):
        """Hook stops immediately at step 1 — no LLM call at all."""

        def immediate_stop(ctx: PrepareStepContext):
            return PrepareStepResult(stop=True, metadata={"stop_message": "Blocked"})

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[immediate_stop],
        )

        responses = [AIMessage(content="Should not be called.")]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])

        # LLM never called
        assert len(llm_inputs) == 0
        assert any("Blocked" in str(getattr(m, "content", "")) for m in messages)


# ---------------------------------------------------------------------------
# Tests: Async Hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepAsync:
    """Async hook support."""

    async def test_async_hook_works(self):
        """Async hook is awaited and result applied."""

        async def async_hook(ctx: PrepareStepContext):
            if ctx.step_number == 1:
                new_msgs = list(ctx.messages) + [HumanMessage(content="[ASYNC_INJECTED]")]
                return PrepareStepResult(messages=new_msgs)
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[async_hook],
        )

        responses = [AIMessage(content="Done.")]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])

        first_call = llm_inputs[0]
        contents = [str(getattr(m, "content", "")) for m in first_call]
        assert any("[ASYNC_INJECTED]" in c for c in contents)


# ---------------------------------------------------------------------------
# Tests: Error Tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepErrorTolerance:
    """Hook exceptions don't break the loop."""

    async def test_exception_in_hook_continues(self):
        """Hook raises exception — loop continues normally."""

        def bad_hook(ctx: PrepareStepContext):
            raise ValueError("Hook crashed!")

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[bad_hook],
        )

        responses = [AIMessage(content="Done.")]

        messages, llm_inputs = await _build_and_run(request, responses, [search_tool])

        # LLM still called despite hook failure
        assert len(llm_inputs) == 1

    async def test_second_hook_runs_after_first_fails(self):
        """Multiple hooks — second runs even if first crashes."""
        captured = []

        def failing_hook(ctx: PrepareStepContext):
            raise RuntimeError("oops")

        def working_hook(ctx: PrepareStepContext):
            captured.append(ctx.step_number)
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[failing_hook, working_hook],
        )

        responses = [AIMessage(content="Done.")]

        await _build_and_run(request, responses, [search_tool])

        assert 1 in captured


# ---------------------------------------------------------------------------
# Tests: Multiple Hooks Chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPrepareStepChaining:
    """Multiple hooks applied sequentially."""

    async def test_hooks_chain_modifications(self):
        """Second hook sees modifications from first hook via shared metadata."""
        order = []

        def hook_a(ctx: PrepareStepContext):
            order.append("a")
            return PrepareStepResult(metadata={"from_a": True})

        def hook_b(ctx: PrepareStepContext):
            order.append("b")
            # ctx.metadata should have been updated by hook_a's result
            if ctx.metadata.get("from_a"):
                order.append("b_saw_a")
            return None

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            prepare_step_hooks=[hook_a, hook_b],
        )

        responses = [AIMessage(content="Done.")]

        await _build_and_run(request, responses, [search_tool])

        assert order == ["a", "b", "b_saw_a"]
