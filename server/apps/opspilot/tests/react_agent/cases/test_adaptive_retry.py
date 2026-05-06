"""
Tests for adaptive tool retry in the ReAct agent loop.

Verifies that when a tool execution fails, the logged_tool_node automatically
retries with exponential backoff, and replaces the error result on success.

Key behaviors:
- Retry triggered by error content (starts with "Error:" or "Traceback", or contains keywords)
- Configurable max retries, backoff, and error keywords
- Successful retry replaces the error ToolMessage
- Exhausted retries preserve original error for LLM to handle
- Can be disabled via retry_config.enabled=False
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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, RetryConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

_call_counter = {"n": 0}


@tool
def flaky_tool(query: str) -> str:
    """A tool that fails on first calls then succeeds."""
    _call_counter["n"] += 1
    if _call_counter["n"] <= 2:
        raise RuntimeError("Error: connection timeout")
    return f"success: {query}"


@tool
def always_fails(query: str) -> str:
    """A tool that always fails."""
    raise RuntimeError("Error: service unavailable (503)")


@tool
def always_works(query: str) -> str:
    """A tool that always works."""
    return f"result: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools):
    """Build ReAct graph with given tools and mock LLM, run and return final messages + steps."""
    node_builder = ToolsNodes()
    node_builder.tools = tools

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

    return result.get("messages", []), call_count["n"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolRetryBasic:
    """Basic retry behavior."""

    async def test_first_fail_then_succeed(self):
        """Tool fails first call, retries succeed — final result is success."""
        # Use always_works for the actual tool (ToolNode uses the real tool)
        # We need a tool that fails then succeeds.
        # Since ToolNode calls the real tool, we use a stateful tool.
        call_state = {"n": 0}

        @tool
        def fail_then_succeed(query: str) -> str:
            """Fails first, succeeds second."""
            call_state["n"] += 1
            if call_state["n"] <= 1:
                raise RuntimeError("Error: connection timeout")
            return f"success: {query}"

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=True, max_retries_per_tool=2, backoff_seconds=0.01),
        )
        responses = [
            AIMessage(
                content="Let me look up",
                tool_calls=[{"name": "fail_then_succeed", "args": {"query": "test"}, "id": "call_1"}],
            ),
            AIMessage(content="Done."),  # natural end after tool succeeds
        ]

        messages, steps = await _build_and_run(request, responses, [fail_then_succeed])

        # The tool was retried and succeeded — LLM got success result and ended
        assert steps == 2
        # Find the tool message in the conversation
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any(
            "success" in str(m.content) for m in tool_msgs
        ), f"Expected a successful tool result after retry, got: {[m.content for m in tool_msgs]}"

    async def test_retries_exhausted_preserves_error(self):
        """Tool always fails — after max retries, error is preserved for LLM."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=True, max_retries_per_tool=2, backoff_seconds=0.01),
        )
        responses = [
            AIMessage(
                content="Calling tool",
                tool_calls=[{"name": "always_fails", "args": {"query": "x"}, "id": "call_1"}],
            ),
            AIMessage(content="Tool failed, giving up."),
        ]

        messages, steps = await _build_and_run(request, responses, [always_fails])

        # LLM ran twice: first call triggered tool (which failed), second ended naturally
        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # The error should still be there (retries exhausted, original error preserved)
        assert any("Error" in str(m.content) or "503" in str(m.content) for m in tool_msgs)

    async def test_successful_tool_no_retry(self):
        """Tool succeeds on first try — no retry attempted."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=True, max_retries_per_tool=3, backoff_seconds=0.01),
        )
        responses = [
            AIMessage(
                content="Calling",
                tool_calls=[{"name": "always_works", "args": {"query": "hello"}, "id": "call_1"}],
            ),
            AIMessage(content="Got the result."),
        ]

        messages, steps = await _build_and_run(request, responses, [always_works])

        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        assert any("result: hello" in str(m.content) for m in tool_msgs)


@pytest.mark.asyncio
class TestToolRetryDisabled:
    """Retry disabled."""

    async def test_disabled_no_retry(self):
        """When retry_config.enabled=False, no retry even on error."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
        )
        responses = [
            AIMessage(
                content="Calling",
                tool_calls=[{"name": "always_fails", "args": {"query": "x"}, "id": "call_1"}],
            ),
            AIMessage(content="Failed."),
        ]

        messages, steps = await _build_and_run(request, responses, [always_fails])

        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Error preserved, no retry
        assert any("Error" in str(m.content) or "503" in str(m.content) for m in tool_msgs)


@pytest.mark.asyncio
class TestToolRetryKeywords:
    """Keyword-based error detection."""

    async def test_keyword_triggers_retry(self):
        """Error containing 'timeout' triggers retry."""
        call_state = {"n": 0}

        @tool
        def timeout_then_ok(query: str) -> str:
            """Timeout first, ok second."""
            call_state["n"] += 1
            if call_state["n"] <= 1:
                return "Error: request timeout after 30s"
            return "success"

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(
                enabled=True,
                max_retries_per_tool=2,
                backoff_seconds=0.01,
                retry_on_error_keywords=["timeout", "connection"],
            ),
        )
        responses = [
            AIMessage(
                content="Calling",
                tool_calls=[{"name": "timeout_then_ok", "args": {"query": "x"}, "id": "call_1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, steps = await _build_and_run(request, responses, [timeout_then_ok])

        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Should have retried and gotten success
        assert any("success" in str(m.content) for m in tool_msgs)

    async def test_non_matching_error_no_retry(self):
        """Error without matching keywords is NOT retried."""

        @tool
        def validation_error(query: str) -> str:
            """Returns a validation error."""
            return "Invalid parameter: query must be non-empty"

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(
                enabled=True,
                max_retries_per_tool=3,
                backoff_seconds=0.01,
                retry_on_error_keywords=["timeout", "connection", "500"],
            ),
        )
        responses = [
            AIMessage(
                content="Calling",
                tool_calls=[{"name": "validation_error", "args": {"query": ""}, "id": "call_1"}],
            ),
            AIMessage(content="Got validation error."),
        ]

        messages, steps = await _build_and_run(request, responses, [validation_error])

        assert steps == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # No retry — "Invalid parameter" doesn't match keywords and doesn't start with "Error:"
        assert any("Invalid parameter" in str(m.content) for m in tool_msgs)


@pytest.mark.asyncio
class TestToolRetryBackoff:
    """Exponential backoff timing."""

    async def test_backoff_increases(self):
        """Verify sleep is called with exponential backoff times."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=True, max_retries_per_tool=3, backoff_seconds=1.0),
        )
        responses = [
            AIMessage(
                content="Calling",
                tool_calls=[{"name": "always_fails", "args": {"query": "x"}, "id": "call_1"}],
            ),
            AIMessage(content="Failed after retries."),
        ]

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)
            # Don't actually sleep

        with patch("asyncio.sleep", side_effect=mock_sleep):
            messages, steps = await _build_and_run(request, responses, [always_fails])

        # 3 retries with backoff: 1*2^0=1, 1*2^1=2, 1*2^2=4
        assert len(sleep_calls) == 3, f"Expected 3 sleep calls, got {len(sleep_calls)}"
        assert sleep_calls[0] == 1.0
        assert sleep_calls[1] == 2.0
        assert sleep_calls[2] == 4.0
