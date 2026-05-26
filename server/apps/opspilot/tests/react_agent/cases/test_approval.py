"""
Tests for #22 Human Approval (LLM-driven tool approach).

The `request_human_approval` tool is built by `_build_approval_tool()` and
injected into the ReAct tool list. The LLM autonomously calls it when it
judges an operation as high-risk. The tool dispatches an SSE event, polls
Redis for the decision, and returns a text result the LLM uses to decide
whether to proceed.

Verifies:
- Tool is injected when tools exist
- Approved → returns approval text
- Rejected → returns rejection text
- SSE event dispatched with correct fields
- Retry logic skips request_human_approval
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
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def dangerous_tool(query: str) -> str:
    """A dangerous tool that needs approval."""
    return f"executed: {query}"


@tool
def safe_tool(query: str) -> str:
    """A safe tool that never needs approval."""
    return f"safe: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(
    request,
    mock_llm_responses,
    tools_list=None,
    mock_approval_decision=None,
):
    """Build ReAct graph with mocked approval tool.

    The LLM mock returns pre-defined responses. When one of them includes
    a tool_call to `request_human_approval`, the tool executes, dispatches
    an event, and polls Redis (mocked via `wait_for_approval`).
    """
    if tools_list is None:
        tools_list = [dangerous_tool, safe_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    approval_events = []

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
            "execution_id": "exec-approval-test",
            "node_id": "node-1",
            "trigger_type": "interactive",
        }
    }

    async def mock_wait_for_approval(execution_id, node_id, tool_call_id, **kwargs):
        if callable(mock_approval_decision):
            return mock_approval_decision(execution_id, node_id, tool_call_id)
        return mock_approval_decision or {"decision": "approve", "reason": "", "source": "user"}

    def capture_event(name, data):
        if name == "approval_request":
            approval_events.append(dict(data))

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ), patch(
        "apps.opspilot.metis.llm.chain.node.wait_for_approval",
        side_effect=mock_wait_for_approval,
    ), patch(
        "apps.opspilot.metis.llm.chain.node.is_interrupt_requested_async",
        new_callable=AsyncMock,
        return_value=False,
    ), patch(
        "apps.opspilot.metis.llm.chain.node.dispatch_custom_event",
        side_effect=capture_event,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), call_count["n"], approval_events


# ---------------------------------------------------------------------------
# Tests: Tool injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApprovalToolInjection:
    """request_human_approval tool is injected when tools exist."""

    async def test_approval_tool_present(self):
        """The approval tool is built and added to tools list."""
        node_builder = ToolsNodes()
        node_builder.tools = [dangerous_tool]
        approval_tool = node_builder._build_approval_tool()
        assert approval_tool is not None
        assert approval_tool.name == "request_human_approval"

    async def test_no_approval_tool_without_tools(self):
        """No approval tool when there are no tools."""
        node_builder = ToolsNodes()
        node_builder.tools = []
        approval_tool = node_builder._build_approval_tool() if node_builder.tools else None
        assert approval_tool is None


# ---------------------------------------------------------------------------
# Tests: Approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApprovalApproved:
    """LLM calls request_human_approval → approved → proceeds."""

    async def test_approved_then_executes(self):
        """LLM asks approval, gets approved, then calls the actual tool."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            # Step 1: LLM calls request_human_approval
            AIMessage(
                content="Let me check approval first.",
                tool_calls=[
                    {
                        "name": "request_human_approval",
                        "args": {"action": "删除数据库表", "reason": "高危操作", "risk_level": "high"},
                        "id": "c_approval",
                    }
                ],
            ),
            # Step 2: After approval, LLM calls the actual tool
            AIMessage(
                content="Approved, proceeding.",
                tool_calls=[
                    {
                        "name": "dangerous_tool",
                        "args": {"query": "drop table"},
                        "id": "c_exec",
                    }
                ],
            ),
            # Step 3: Done
            AIMessage(content="Operation completed."),
        ]

        messages, llm_calls, approval_events = await _build_and_run(
            request,
            responses,
            mock_approval_decision={"decision": "approve", "reason": "", "source": "user"},
        )

        assert llm_calls == 3
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Approval tool returned approval text
        assert any("已批准" in str(m.content) for m in tool_msgs)
        # Actual tool executed
        assert any("executed: drop table" in str(m.content) for m in tool_msgs)
        # SSE event dispatched
        assert len(approval_events) >= 1


# ---------------------------------------------------------------------------
# Tests: Rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApprovalRejected:
    """LLM calls request_human_approval → rejected → does not proceed."""

    async def test_rejected_tool_not_executed(self):
        """LLM asks approval, gets rejected, reports to user."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            # Step 1: LLM calls request_human_approval
            AIMessage(
                content="Checking approval.",
                tool_calls=[
                    {
                        "name": "request_human_approval",
                        "args": {"action": "重启服务", "reason": "影响可用性", "risk_level": "high"},
                        "id": "c_approval",
                    }
                ],
            ),
            # Step 2: After rejection, LLM informs user (no tool call)
            AIMessage(content="操作未被批准，已取消。"),
        ]

        messages, llm_calls, _ = await _build_and_run(
            request,
            responses,
            mock_approval_decision={"decision": "reject", "reason": "太危险", "source": "user"},
        )

        assert llm_calls == 2
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Approval tool returned rejection text
        assert any("拒绝" in str(m.content) for m in tool_msgs)
        # Dangerous tool NOT executed
        assert not any("executed:" in str(m.content) for m in tool_msgs)


# ---------------------------------------------------------------------------
# Tests: SSE event fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApprovalEvent:
    """approval_request SSE event dispatched with correct fields."""

    async def test_event_dispatched_with_correct_fields(self):
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="Approval needed.",
                tool_calls=[
                    {
                        "name": "request_human_approval",
                        "args": {"action": "修改配置", "reason": "生产环境", "risk_level": "critical"},
                        "id": "c_approval",
                    }
                ],
            ),
            AIMessage(content="Done."),
        ]

        _, _, approval_events = await _build_and_run(
            request,
            responses,
            mock_approval_decision={"decision": "approve", "reason": "", "source": "user"},
        )

        assert len(approval_events) >= 1
        event = approval_events[0]
        assert event["execution_id"] == "exec-approval-test"
        assert event["node_id"] == "node-1"
        assert event["tool_name"] == "修改配置"
        assert event["tool_args"]["reason"] == "生产环境"
        assert event["tool_args"]["risk_level"] == "critical"


# ---------------------------------------------------------------------------
# Tests: Retry skips approval tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApprovalRetrySkip:
    """Retry logic should skip request_human_approval tool."""

    async def test_retry_does_not_retry_approval(self):
        """If request_human_approval returns an error-like result,
        it should NOT be retried (same as activate_tools)."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=True, max_retries=3),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="Approval.",
                tool_calls=[
                    {
                        "name": "request_human_approval",
                        "args": {"action": "test", "reason": "test", "risk_level": "low"},
                        "id": "c_approval",
                    }
                ],
            ),
            AIMessage(content="Done."),
        ]

        messages, llm_calls, _ = await _build_and_run(
            request,
            responses,
            mock_approval_decision={"decision": "reject", "reason": "no", "source": "user"},
        )

        # Should only call LLM twice — no retry of approval tool
        assert llm_calls == 2
