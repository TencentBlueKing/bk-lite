"""
Tests for #23 执行后验证 (Post-execution Verification).

Verifies:
- Verification triggered for tools with spec (registry/metadata/override)
- Verification result injected as SystemMessage
- verification_started + verification_completed events dispatched
- Disabled config skips verification
- No spec found → no verification
- Config overrides take priority over registry/metadata
- Missing verify tool → graceful skip
- Error tool results → no verification triggered
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
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import (  # noqa: E402
    BasicLLMRequest,
    ReflectionConfig,
    RetryConfig,
    TimeoutConfig,
    ToolVerificationSpec,
    VerificationConfig,
)
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def restart_pod(pod_name: str, namespace: str = "default") -> str:
    """Restart a Kubernetes pod."""
    return f"Pod {pod_name} in {namespace} restarted successfully"


@tool
def get_pod_details(pod_name: str, namespace: str = "default") -> str:
    """Get pod details for verification."""
    return f"Pod {pod_name} in {namespace}: status=Running, restarts=1"


@tool
def simple_tool(query: str) -> str:
    """A simple tool with no verification spec."""
    return f"result: {query}"


@tool
def meta_tool(action: str) -> str:
    """A tool with verification in metadata."""
    return f"done: {action}"


# Attach verification metadata to meta_tool
meta_tool.metadata = {
    "verification": {
        "verify_tool": "simple_tool",
        "args_mapping": {"query": "action"},
        "delay_seconds": 0.0,
        "description": "Verify meta_tool action",
    }
}


@tool
def failing_tool(query: str) -> str:
    """A tool that always fails."""
    raise RuntimeError("Error: tool crashed")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _build_and_run(request, mock_llm_responses, tools_list):
    """Build ReAct graph, capture verification events."""
    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    custom_events = []

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

    config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": ""}}

    def capture_event(name, data):
        custom_events.append({"name": name, "data": dict(data)})

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ), patch(
        "langchain_core.callbacks.dispatch_custom_event",
        side_effect=capture_event,
    ), patch(
        "apps.opspilot.metis.llm.chain.node.is_interrupt_requested",
        return_value=False,
    ), patch(
        "asyncio.sleep",
        return_value=None,
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), custom_events


# ---------------------------------------------------------------------------
# Tests: Verification triggered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationTriggered:
    """Verification triggered for tools with spec."""

    async def test_registry_spec_triggers_verification(self):
        """Tool in VERIFICATION_REGISTRY triggers verification, result injected as SystemMessage."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="restarting",
                tool_calls=[{"name": "restart_pod", "args": {"pod_name": "web-1", "namespace": "prod"}, "id": "c1"}],
            ),
            AIMessage(content="Pod restarted and verified."),
        ]

        messages, events = await _build_and_run(request, responses, [restart_pod, get_pod_details])

        # Verification result should be injected as SystemMessage
        sys_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        verify_sys = [m for m in sys_msgs if "执行后验证" in str(m.content)]
        assert len(verify_sys) >= 1, f"Expected verification SystemMessage, got sys_msgs: {[m.content[:80] for m in sys_msgs]}"
        assert "get_pod_details" in str(verify_sys[0].content)
        assert "Running" in str(verify_sys[0].content)

    async def test_metadata_spec_triggers_verification(self):
        """Tool with verification metadata triggers verification."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="acting",
                tool_calls=[{"name": "meta_tool", "args": {"action": "deploy"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run(request, responses, [meta_tool, simple_tool])

        sys_msgs = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(sys_msgs) >= 1
        assert "simple_tool" in str(sys_msgs[0].content)


# ---------------------------------------------------------------------------
# Tests: Events dispatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationEvents:
    """verification_started + verification_completed events."""

    async def test_events_dispatched(self):
        """Both verification events dispatched with correct fields."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="restarting",
                tool_calls=[{"name": "restart_pod", "args": {"pod_name": "web-1", "namespace": "prod"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        _, events = await _build_and_run(request, responses, [restart_pod, get_pod_details])

        started = [e for e in events if e["name"] == "verification_started"]
        completed = [e for e in events if e["name"] == "verification_completed"]

        assert len(started) >= 1
        assert started[0]["data"]["action_tool"] == "restart_pod"
        assert started[0]["data"]["verify_tool"] == "get_pod_details"

        assert len(completed) >= 1
        assert completed[0]["data"]["action_tool"] == "restart_pod"
        assert completed[0]["data"]["attempts"] >= 1


# ---------------------------------------------------------------------------
# Tests: Disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationDisabled:
    """Disabled config skips verification."""

    async def test_disabled_no_verification(self):
        """When disabled, no verification SystemMessage or events."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="restarting",
                tool_calls=[{"name": "restart_pod", "args": {"pod_name": "web-1", "namespace": "prod"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(request, responses, [restart_pod, get_pod_details])

        verify_sys = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(verify_sys) == 0

        verify_events = [e for e in events if "verification" in e["name"]]
        assert len(verify_events) == 0


# ---------------------------------------------------------------------------
# Tests: No spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationNoSpec:
    """Tool without verification spec → no verification."""

    async def test_no_spec_skipped(self):
        """Tool not in registry/metadata/overrides skips verification."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="querying",
                tool_calls=[{"name": "simple_tool", "args": {"query": "hello"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(request, responses, [simple_tool])

        verify_sys = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(verify_sys) == 0


# ---------------------------------------------------------------------------
# Tests: Config overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationOverrides:
    """Config overrides take priority."""

    async def test_override_spec_used(self):
        """Override spec for simple_tool → verification triggered using override."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(
                enabled=True,
                overrides={
                    "simple_tool": ToolVerificationSpec(
                        verify_tool="simple_tool",
                        args_mapping={"query": "query"},
                        delay_seconds=0.0,
                        description="Custom verify for simple_tool",
                    ),
                },
            ),
        )

        responses = [
            AIMessage(
                content="querying",
                tool_calls=[{"name": "simple_tool", "args": {"query": "check"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run(request, responses, [simple_tool])

        verify_sys = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(verify_sys) >= 1
        assert "Custom verify" in str(verify_sys[0].content)


# ---------------------------------------------------------------------------
# Tests: Missing verify tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationMissingTool:
    """Verify tool not available → graceful skip."""

    async def test_missing_verify_tool_graceful(self):
        """Registry spec points to nonexistent verify tool → skip with message."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="restarting",
                tool_calls=[{"name": "restart_pod", "args": {"pod_name": "web-1", "namespace": "prod"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        # Only restart_pod, NOT get_pod_details → verify tool missing
        messages, _ = await _build_and_run(request, responses, [restart_pod])

        # Should have verification SystemMessage with "不可用" message
        verify_sys = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(verify_sys) >= 1
        assert "不可用" in str(verify_sys[0].content)


# ---------------------------------------------------------------------------
# Tests: Error result not verified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestVerificationErrorSkipped:
    """Failed tool results are not verified."""

    async def test_error_result_not_verified(self):
        """Tool that returns error → no verification triggered."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(
                enabled=True,
                overrides={
                    "failing_tool": ToolVerificationSpec(
                        verify_tool="simple_tool",
                        args_mapping={"query": "query"},
                        description="Should not run",
                    ),
                },
            ),
        )

        responses = [
            AIMessage(
                content="trying",
                tool_calls=[{"name": "failing_tool", "args": {"query": "x"}, "id": "c1"}],
            ),
            AIMessage(content="Failed."),
        ]

        messages, events = await _build_and_run(request, responses, [failing_tool, simple_tool])

        verify_sys = [m for m in messages if isinstance(m, SystemMessage) and "执行后验证" in str(m.content)]
        assert len(verify_sys) == 0

        verify_events = [e for e in events if "verification" in e["name"]]
        assert len(verify_events) == 0
