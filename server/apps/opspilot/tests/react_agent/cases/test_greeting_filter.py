"""
Regression tests for the first-turn greeting filter.

Verifies:
- pure K8s scenes still clear tools for obvious greetings
- current_time-only scenes keep their tool binding on short time queries
- mixed K8s + current_time scenes also keep their tool binding
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
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import (  # noqa: E402
    BasicLLMRequest,
    ReflectionConfig,
    RetryConfig,
    TimeoutConfig,
    ToolsServer,
)
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """Return the current time."""
    return f"time:{timezone}"


@tool
def get_current_cluster_name() -> str:
    """Return the current Kubernetes cluster name."""
    return "test-cluster"


class AgentState(dict):
    messages: Annotated[list, add_messages]


async def _build_and_run(request, first_user_message, tools_list):
    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    bound_tool_names = []

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="done"))

    def track_bind(tools_arg, **kwargs):
        ignored = {"request_human_approval", "request_user_choice"}
        bound_tool_names.append([tool_item.name for tool_item in tools_arg if tool_item.name not in ignored])
        bound = MagicMock()
        bound.ainvoke = AsyncMock(return_value=AIMessage(content="done"))
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

    config = {"configurable": {"graph_request": request, "trace_id": "test", "execution_id": ""}}

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ):
        await graph.ainvoke({"messages": [HumanMessage(content=first_user_message)]}, config=config)

    return bound_tool_names[0] if bound_tool_names else []


@pytest.mark.asyncio
async def test_k8s_only_greeting_still_clears_tools():
    request = BasicLLMRequest(
        model="gpt-4o",
        max_steps=3,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        tools_servers=[ToolsServer(name="kubernetes", url="langchain:kubernetes")],
    )

    first_bind_tool_names = await _build_and_run(request, "你好", [get_current_cluster_name])

    assert "get_current_cluster_name" not in first_bind_tool_names


@pytest.mark.asyncio
async def test_current_time_short_request_keeps_time_tool_bound():
    request = BasicLLMRequest(
        model="gpt-4o",
        max_steps=3,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        tools_servers=[ToolsServer(name="current_time", url="langchain:current_time")],
    )

    first_bind_tool_names = await _build_and_run(request, "现在几点了", [get_current_time])

    assert "get_current_time" in first_bind_tool_names


@pytest.mark.asyncio
async def test_mixed_k8s_and_current_time_short_request_keeps_tools_bound():
    request = BasicLLMRequest(
        model="gpt-4o",
        max_steps=3,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        tools_servers=[
            ToolsServer(name="kubernetes", url="langchain:kubernetes"),
            ToolsServer(name="current_time", url="langchain:current_time"),
        ],
    )

    first_bind_tool_names = await _build_and_run(
        request,
        "几点了",
        [get_current_cluster_name, get_current_time],
    )

    assert "get_current_cluster_name" in first_bind_tool_names
    assert "get_current_time" in first_bind_tool_names


@pytest.mark.asyncio
async def test_k8s_with_non_langchain_server_keeps_tools_bound():
    request = BasicLLMRequest(
        model="gpt-4o",
        max_steps=3,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        tools_servers=[
            ToolsServer(name="kubernetes", url="langchain:kubernetes"),
            ToolsServer(name="external_mcp", url="https://example.com/mcp"),
        ],
    )

    first_bind_tool_names = await _build_and_run(request, "你好", [get_current_cluster_name])

    assert "get_current_cluster_name" in first_bind_tool_names


@pytest.mark.asyncio
async def test_k8s_with_unknown_langchain_server_keeps_tools_bound():
    request = BasicLLMRequest(
        model="gpt-4o",
        max_steps=3,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        tools_servers=[
            ToolsServer(name="kubernetes", url="langchain:kubernetes"),
            ToolsServer(name="unknown", url="langchain:foo"),
        ],
    )

    first_bind_tool_names = await _build_and_run(request, "你好", [get_current_cluster_name])

    assert "get_current_cluster_name" in first_bind_tool_names
