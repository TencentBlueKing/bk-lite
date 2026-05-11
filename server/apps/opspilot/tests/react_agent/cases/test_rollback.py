"""
Tests for #24 操作回滚 (Post-execution Rollback).

Verifies:
- auto strategy: executes rollback tool automatically, dispatches events
- prompt strategy: injects snapshot + rollback context as SystemMessage
- none strategy: no rollback action or injection
- disabled config: skips all rollback logic
- metadata spec: tool.metadata["rollback"] triggers correctly
- config overrides: take priority over registry/metadata
- no spec: tool without rollback spec → no rollback messages
- snapshot captured: snapshot tool called before action
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
    RollbackConfig,
    TimeoutConfig,
    ToolRollbackSpec,
    VerificationConfig,
)
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def scale_deployment(deployment_name: str, namespace: str = "default", replicas: int = 1) -> str:
    """Scale a Kubernetes deployment."""
    return f"Deployment {deployment_name} in {namespace} scaled to {replicas} replicas"


@tool
def list_kubernetes_deployments(namespace: str = "default") -> str:
    """List deployments for snapshot."""
    return '{"items": [{"metadata": {"name": "web"}, "spec": {"replicas": 3}}]}'


@tool
def rollback_scale(deployment_name: str, namespace: str = "default", replicas: int = 1) -> str:
    """Rollback scaling."""
    return f"Rolled back {deployment_name} in {namespace} to {replicas} replicas"


@tool
def restart_pod(pod_name: str, namespace: str = "default") -> str:
    """Restart a pod (non-rollbackable)."""
    return f"Pod {pod_name} restarted"


@tool
def meta_rollback_tool(action: str) -> str:
    """Tool with rollback metadata."""
    return f"executed: {action}"


@tool
def meta_snapshot_tool(action: str) -> str:
    """Snapshot tool for meta_rollback_tool."""
    return f"snapshot of: {action}"


@tool
def meta_rb_executor(action: str) -> str:
    """Rollback executor for meta_rollback_tool."""
    return f"rolled back: {action}"


# Attach rollback metadata
meta_rollback_tool.metadata = {
    "rollback": {
        "snapshot_tool": "meta_snapshot_tool",
        "snapshot_args_mapping": {"action": "action"},
        "rollback_tool": "meta_rb_executor",
        "rollback_args_mapping": {"action": "action"},
        "rollback_snapshot_args": {},
        "strategy": "auto",
        "description": "Auto rollback via metadata",
    }
}


@tool
def simple_tool(query: str) -> str:
    """Simple tool with no rollback spec."""
    return f"result: {query}"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(dict):
    messages: Annotated[list, add_messages]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

# Patch the ROLLBACK_REGISTRY for tests
TEST_ROLLBACK_REGISTRY = {
    "scale_deployment": ToolRollbackSpec(
        snapshot_tool="list_kubernetes_deployments",
        snapshot_args_mapping={"namespace": "namespace"},
        rollback_tool="rollback_scale",
        rollback_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
        rollback_snapshot_args={"replicas": "items.0.spec.replicas"},
        strategy="auto",
        description="Auto rollback scaling",
    ),
    "restart_pod": ToolRollbackSpec(
        snapshot_tool=None,
        rollback_tool=None,
        strategy="none",
        description="Pod restart not rollbackable",
    ),
}


async def _build_and_run(request, mock_llm_responses, tools_list, registry_patch=None):
    """Build ReAct graph, capture rollback events."""
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

    patches = [
        patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ),
        patch(
            "langchain_core.callbacks.dispatch_custom_event",
            side_effect=capture_event,
        ),
        patch(
            "apps.opspilot.metis.llm.chain.node.is_interrupt_requested",
            return_value=False,
        ),
        patch("asyncio.sleep", return_value=None),
    ]
    if registry_patch is not None:
        patches.append(patch("apps.opspilot.utils.rollback.ROLLBACK_REGISTRY", registry_patch))

    with patches[0], patches[1], patches[2], patches[3]:
        if registry_patch is not None:
            with patches[4]:
                result = await graph.ainvoke(
                    {"messages": [HumanMessage(content="test")]},
                    config=config,
                )
        else:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

    return result.get("messages", []), custom_events


# ---------------------------------------------------------------------------
# Tests: Auto strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackAuto:
    """Auto strategy triggers rollback tool and dispatches events."""

    async def test_auto_rollback_executes(self):
        """strategy=auto executes rollback_scale and injects SystemMessage."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True, auto_rollback_on_verify_fail=True),
        )

        responses = [
            AIMessage(
                content="scaling",
                tool_calls=[{"name": "scale_deployment", "args": {"deployment_name": "web", "namespace": "prod", "replicas": 5}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [scale_deployment, list_kubernetes_deployments, rollback_scale],
            registry_patch=TEST_ROLLBACK_REGISTRY,
        )

        # Should have rollback SystemMessage
        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and "操作回滚" in str(m.content)]
        assert len(rb_sys) >= 1
        assert "rollback_scale" in str(rb_sys[0].content) or "回滚" in str(rb_sys[0].content)

        # Events
        started = [e for e in events if e["name"] == "rollback_started"]
        completed = [e for e in events if e["name"] == "rollback_completed"]
        assert len(started) >= 1
        assert started[0]["data"]["action_tool"] == "scale_deployment"
        assert len(completed) >= 1
        assert completed[0]["data"]["rolled_back"] is True


# ---------------------------------------------------------------------------
# Tests: Prompt strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackPrompt:
    """Prompt strategy injects context without executing rollback."""

    async def test_prompt_injects_context(self):
        """strategy=prompt injects snapshot + rollback info as SystemMessage."""
        prompt_registry = {
            "scale_deployment": ToolRollbackSpec(
                snapshot_tool="list_kubernetes_deployments",
                snapshot_args_mapping={"namespace": "namespace"},
                rollback_tool="rollback_scale",
                rollback_args_mapping={"deployment_name": "deployment_name", "namespace": "namespace"},
                rollback_snapshot_args={},
                strategy="prompt",
                description="Prompt user to decide rollback",
            ),
        }

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="scaling",
                tool_calls=[{"name": "scale_deployment", "args": {"deployment_name": "web", "namespace": "prod", "replicas": 5}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [scale_deployment, list_kubernetes_deployments, rollback_scale],
            registry_patch=prompt_registry,
        )

        # Should have "回滚可用" SystemMessage
        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and "回滚可用" in str(m.content)]
        assert len(rb_sys) >= 1
        assert "rollback_scale" in str(rb_sys[0].content)
        assert "snapshot" in str(rb_sys[0].content).lower() or "快照" in str(rb_sys[0].content)

        # No rollback_started event (not auto)
        started = [e for e in events if e["name"] == "rollback_started"]
        assert len(started) == 0


# ---------------------------------------------------------------------------
# Tests: None strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackNone:
    """None strategy produces no rollback action."""

    async def test_none_strategy_skipped(self):
        """strategy=none → no rollback messages or events."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="restarting",
                tool_calls=[{"name": "restart_pod", "args": {"pod_name": "web-1", "namespace": "prod"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [restart_pod],
            registry_patch=TEST_ROLLBACK_REGISTRY,
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and ("操作回滚" in str(m.content) or "回滚可用" in str(m.content))]
        assert len(rb_sys) == 0

        rb_events = [e for e in events if "rollback" in e["name"]]
        assert len(rb_events) == 0


# ---------------------------------------------------------------------------
# Tests: Disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackDisabled:
    """Disabled config skips all rollback logic."""

    async def test_disabled_no_rollback(self):
        """rollback_config.enabled=False → no rollback."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="scaling",
                tool_calls=[{"name": "scale_deployment", "args": {"deployment_name": "web", "namespace": "prod", "replicas": 5}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [scale_deployment, list_kubernetes_deployments, rollback_scale],
            registry_patch=TEST_ROLLBACK_REGISTRY,
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and ("操作回滚" in str(m.content) or "回滚可用" in str(m.content))]
        assert len(rb_sys) == 0

        rb_events = [e for e in events if "rollback" in e["name"]]
        assert len(rb_events) == 0


# ---------------------------------------------------------------------------
# Tests: Metadata spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackMetadata:
    """Tool metadata rollback spec triggers correctly."""

    async def test_metadata_auto_rollback(self):
        """tool.metadata['rollback'] with strategy=auto triggers rollback."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True, auto_rollback_on_verify_fail=True),
        )

        responses = [
            AIMessage(
                content="acting",
                tool_calls=[{"name": "meta_rollback_tool", "args": {"action": "deploy"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [meta_rollback_tool, meta_snapshot_tool, meta_rb_executor],
            registry_patch={},  # empty registry, rely on metadata
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and "操作回滚" in str(m.content)]
        assert len(rb_sys) >= 1
        assert "meta_rb_executor" in str(rb_sys[0].content) or "rolled back" in str(rb_sys[0].content)

        started = [e for e in events if e["name"] == "rollback_started"]
        assert len(started) >= 1


# ---------------------------------------------------------------------------
# Tests: Config overrides
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackOverrides:
    """Config overrides take priority over registry and metadata."""

    async def test_override_changes_strategy(self):
        """Override simple_tool to have auto rollback."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(
                enabled=True,
                auto_rollback_on_verify_fail=True,
                overrides={
                    "simple_tool": ToolRollbackSpec(
                        snapshot_tool=None,
                        rollback_tool="simple_tool",
                        rollback_args_mapping={"query": "query"},
                        strategy="auto",
                        description="Custom override rollback",
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

        messages, events = await _build_and_run(
            request,
            responses,
            [simple_tool],
            registry_patch={},
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and "操作回滚" in str(m.content)]
        assert len(rb_sys) >= 1

        started = [e for e in events if e["name"] == "rollback_started"]
        assert len(started) >= 1


# ---------------------------------------------------------------------------
# Tests: No spec
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackNoSpec:
    """Tool without rollback spec produces no rollback messages."""

    async def test_no_spec_no_rollback(self):
        """simple_tool with empty registry → no rollback."""
        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="querying",
                tool_calls=[{"name": "simple_tool", "args": {"query": "hello"}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, events = await _build_and_run(
            request,
            responses,
            [simple_tool],
            registry_patch={},
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and ("操作回滚" in str(m.content) or "回滚可用" in str(m.content))]
        assert len(rb_sys) == 0


# ---------------------------------------------------------------------------
# Tests: Snapshot captured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRollbackSnapshot:
    """Snapshot tool called before action and result used in prompt."""

    async def test_snapshot_in_prompt(self):
        """Prompt strategy includes snapshot content."""
        prompt_registry = {
            "scale_deployment": ToolRollbackSpec(
                snapshot_tool="list_kubernetes_deployments",
                snapshot_args_mapping={"namespace": "namespace"},
                rollback_tool="rollback_scale",
                rollback_args_mapping={"deployment_name": "deployment_name"},
                rollback_snapshot_args={},
                strategy="prompt",
                description="Check snapshot is captured",
            ),
        }

        request = BasicLLMRequest(
            max_steps=5,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
            verification_config=VerificationConfig(enabled=False),
            rollback_config=RollbackConfig(enabled=True),
        )

        responses = [
            AIMessage(
                content="scaling",
                tool_calls=[{"name": "scale_deployment", "args": {"deployment_name": "web", "namespace": "prod", "replicas": 10}, "id": "c1"}],
            ),
            AIMessage(content="Done."),
        ]

        messages, _ = await _build_and_run(
            request,
            responses,
            [scale_deployment, list_kubernetes_deployments, rollback_scale],
            registry_patch=prompt_registry,
        )

        rb_sys = [m for m in messages if isinstance(m, SystemMessage) and "回滚可用" in str(m.content)]
        assert len(rb_sys) >= 1
        # Snapshot content should be present (from list_kubernetes_deployments)
        content = str(rb_sys[0].content)
        assert "replicas" in content or "items" in content
