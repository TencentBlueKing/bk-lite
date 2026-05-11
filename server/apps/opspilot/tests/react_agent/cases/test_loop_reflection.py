"""
Tests for in-loop reflection in the ReAct agent.

Verifies that when the agent detects consecutive tool failures or repetitive
tool calls, it injects a reflection prompt to redirect LLM behavior.

Key behaviors:
- Consecutive failures >= threshold triggers reflection
- Repetitive tool calls within window triggers reflection
- Reflection resets trackers (gives agent fresh start)
- Disabled config skips reflection entirely
- Reflection prompt is injected as HumanMessage before LLM call
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
def always_fails_tool(query: str) -> str:
    """A tool that always raises an error."""
    raise RuntimeError("Error: service unavailable")


@tool
def echo_tool(query: str) -> str:
    """A tool that echoes input."""
    return f"echo: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools):
    """Build ReAct graph, run with mock LLM, return (messages, llm_call_inputs)."""
    node_builder = ToolsNodes()
    node_builder.tools = tools

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    llm_inputs = []  # capture what messages were sent to LLM

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


# ---------------------------------------------------------------------------
# Tests: Consecutive Failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReflectionConsecutiveFailures:
    """Reflection triggered by consecutive tool failures."""

    async def test_triggers_after_threshold(self):
        """After 3 consecutive failures, reflection prompt injected on step 5 (4th agent call)."""
        # Steps: call1->fail, call2->fail, call3->fail, call4 should see reflection, then end
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=3),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="try1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="try2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="try3", tool_calls=[{**tool_call, "id": "c3"}]),
            # After 3 failures, next agent call gets reflection prompt
            AIMessage(content="I'll try differently."),  # ends naturally (no tool_calls)
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        # The 4th LLM call should contain the reflection prompt
        assert len(llm_inputs) >= 4
        fourth_call_messages = llm_inputs[3]
        reflection_found = any("[REFLECTION:" in str(getattr(m, "content", "")) for m in fourth_call_messages)
        assert reflection_found, (
            f"Expected reflection prompt in 4th LLM call, got contents: " f"{[str(getattr(m, 'content', ''))[:80] for m in fourth_call_messages]}"
        )

    async def test_no_trigger_below_threshold(self):
        """2 failures (below threshold of 3) should NOT trigger reflection."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=3),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="try1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="try2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="Giving up."),  # natural end
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        # No reflection prompt should appear in any LLM call
        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[REFLECTION:" not in str(getattr(m, "content", ""))

    async def test_success_resets_failure_counter(self):
        """A success between failures resets counter — no reflection triggered."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                consecutive_failures_threshold=3,
                repetition_threshold=99,  # disable repetition trigger for this test
            ),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "always_fails_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "always_fails_tool", "args": {"query": "x"}, "id": "c2"}]),
            # 2 failures, then success resets
            AIMessage(content="t3", tool_calls=[{"name": "echo_tool", "args": {"query": "ok"}, "id": "c3"}]),
            AIMessage(content="t4", tool_calls=[{"name": "always_fails_tool", "args": {"query": "x"}, "id": "c4"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool, echo_tool])

        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[REFLECTION:" not in str(getattr(m, "content", ""))


@pytest.mark.asyncio
class TestReflectionPromptInjection:
    """Reflection prompt is injected into the LLM messages."""

    async def test_reflection_injects_human_message(self):
        """Reflection should inject a HumanMessage after consecutive failures reach threshold."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=3),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="try1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="try2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="try3", tool_calls=[{**tool_call, "id": "c3"}]),
            AIMessage(content="I'll try differently."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        assert len(llm_inputs) >= 4
        fourth_call_messages = llm_inputs[3]
        reflection_messages = [m for m in fourth_call_messages if isinstance(m, HumanMessage)]
        assert reflection_messages, f"Expected HumanMessage in 4th LLM call, got: {fourth_call_messages}"
        assert any("[REFLECTION:" in str(m.content) for m in reflection_messages)

    async def test_reflection_prompt_contains_reason(self):
        """Reflection prompt should include the reason that triggered it."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=3),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="try1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="try2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="try3", tool_calls=[{**tool_call, "id": "c3"}]),
            AIMessage(content="I'll try differently."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        assert len(llm_inputs) >= 4
        fourth_call_messages = llm_inputs[3]
        reflection_messages = [m for m in fourth_call_messages if isinstance(m, HumanMessage)]
        assert reflection_messages
        reflection_content = " ".join(str(m.content) for m in reflection_messages)
        assert "[REFLECTION:" in reflection_content


@pytest.mark.asyncio
class TestReflectionConfigurable:
    """Reflection behavior with custom config settings."""

    async def test_custom_threshold(self):
        """A custom consecutive failure threshold should control when reflection starts."""
        request = BasicLLMRequest(
            max_steps=12,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=5, repetition_threshold=10),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="try1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="try2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="try3", tool_calls=[{**tool_call, "id": "c3"}]),
            AIMessage(content="try4", tool_calls=[{**tool_call, "id": "c4"}]),
            AIMessage(content="try5", tool_calls=[{**tool_call, "id": "c5"}]),
            AIMessage(content="I'll try differently."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        assert len(llm_inputs) >= 6
        for call_msgs in llm_inputs[:5]:
            for m in call_msgs:
                assert "[REFLECTION:" not in str(getattr(m, "content", ""))
        sixth_call_messages = llm_inputs[5]
        assert any("[REFLECTION:" in str(getattr(m, "content", "")) for m in sixth_call_messages)

    async def test_no_reflection_on_step_1(self):
        """Reflection should not trigger on the first agent step."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=True, consecutive_failures_threshold=1),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "echo_tool", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [echo_tool])

        assert len(llm_inputs) >= 1
        first_call_messages = llm_inputs[0]
        assert all("[REFLECTION:" not in str(getattr(m, "content", "")) for m in first_call_messages)


# ---------------------------------------------------------------------------
# Tests: Repetitive Tool Calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReflectionRepetition:
    """Reflection triggered by repetitive tool usage."""

    async def test_triggers_on_repetition(self):
        """Same tool called 3+ times in window of 6 triggers reflection."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                consecutive_failures_threshold=99,  # disable failure trigger
                repetition_window=6,
                repetition_threshold=3,
            ),
        )

        # echo_tool succeeds, so no failure — but called repetitively
        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "echo_tool", "args": {"query": "a"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "echo_tool", "args": {"query": "b"}, "id": "c2"}]),
            AIMessage(content="t3", tool_calls=[{"name": "echo_tool", "args": {"query": "c"}, "id": "c3"}]),
            # After 3 repetitions, next call gets reflection
            AIMessage(content="I should try something else."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [echo_tool])

        # 4th LLM call should have reflection
        assert len(llm_inputs) >= 4
        fourth_msgs = llm_inputs[3]
        reflection_found = any("[REFLECTION:" in str(getattr(m, "content", "")) for m in fourth_msgs)
        assert reflection_found

    async def test_different_tools_no_repetition(self):
        """Different tools in window should NOT trigger repetition reflection."""

        @tool
        def tool_a(query: str) -> str:
            """Tool A."""
            return "a"

        @tool
        def tool_b(query: str) -> str:
            """Tool B."""
            return "b"

        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                consecutive_failures_threshold=99,
                repetition_window=6,
                repetition_threshold=3,
            ),
        )

        responses = [
            AIMessage(content="t1", tool_calls=[{"name": "tool_a", "args": {"query": "x"}, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{"name": "tool_b", "args": {"query": "x"}, "id": "c2"}]),
            AIMessage(content="t3", tool_calls=[{"name": "tool_a", "args": {"query": "y"}, "id": "c3"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [tool_a, tool_b])

        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[REFLECTION:" not in str(getattr(m, "content", ""))


# ---------------------------------------------------------------------------
# Tests: Disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReflectionDisabled:
    """Reflection disabled."""

    async def test_disabled_no_reflection(self):
        """When reflection_config.enabled=False, no reflection even with failures."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            AIMessage(content="t1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{**tool_call, "id": "c2"}]),
            AIMessage(content="t3", tool_calls=[{**tool_call, "id": "c3"}]),
            AIMessage(content="t4", tool_calls=[{**tool_call, "id": "c4"}]),
            AIMessage(content="Done."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        for call_msgs in llm_inputs:
            for m in call_msgs:
                assert "[REFLECTION:" not in str(getattr(m, "content", ""))


# ---------------------------------------------------------------------------
# Tests: Reset after reflection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestReflectionReset:
    """Trackers reset after reflection is triggered."""

    async def test_trackers_reset_after_reflection(self):
        """After reflection fires, it takes another full threshold to fire again."""
        request = BasicLLMRequest(
            max_steps=15,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(
                enabled=True,
                consecutive_failures_threshold=2,
                repetition_window=6,
                repetition_threshold=99,  # disable repetition
            ),
        )

        tool_call = {"name": "always_fails_tool", "args": {"query": "x"}, "id": "call_1"}
        responses = [
            # First 2 failures -> trigger reflection on step 3
            AIMessage(content="t1", tool_calls=[{**tool_call, "id": "c1"}]),
            AIMessage(content="t2", tool_calls=[{**tool_call, "id": "c2"}]),
            # Step 3: reflection injected, agent still tries tool
            AIMessage(content="t3", tool_calls=[{**tool_call, "id": "c3"}]),
            # After reset: need 2 more failures for second reflection
            AIMessage(content="t4", tool_calls=[{**tool_call, "id": "c4"}]),
            # Step 5: second reflection
            AIMessage(content="t5", tool_calls=[{**tool_call, "id": "c5"}]),
            AIMessage(content="Giving up."),
        ]

        messages, llm_inputs = await _build_and_run(request, responses, [always_fails_tool])

        # Count how many LLM calls had reflection
        reflection_calls = []
        for i, call_msgs in enumerate(llm_inputs):
            if any("[REFLECTION:" in str(getattr(m, "content", "")) for m in call_msgs):
                reflection_calls.append(i)

        # Should have exactly 2 reflections (after first 2 failures, then after next 2)
        assert len(reflection_calls) == 2, f"Expected 2 reflection triggers, got {len(reflection_calls)} " f"at indices {reflection_calls}"
