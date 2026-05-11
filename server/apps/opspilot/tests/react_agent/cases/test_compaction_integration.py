import sys
import types

for _mod_name in ("oracledb", "pyodbc"):
    sys.modules.setdefault(_mod_name, types.ModuleType(_mod_name))

_falkordb = types.ModuleType("falkordb")
setattr(_falkordb, "Graph", type("Graph", (), {}))
sys.modules.setdefault("falkordb", _falkordb)

_falkordb_asyncio = types.ModuleType("falkordb.asyncio")
setattr(_falkordb_asyncio, "FalkorDB", type("FalkorDB", (), {}))
sys.modules.setdefault("falkordb.asyncio", _falkordb_asyncio)

from typing import Annotated, Any, TypedDict  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import (  # noqa: E402
    BasicLLMRequest,
    PrepareStepContext,
    PrepareStepResult,
    ReflectionConfig,
    RetryConfig,
    TimeoutConfig,
)
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402


@tool
def search_tool(query: str) -> str:
    """Search for information."""
    return f"found:{query}"


class AgentState(TypedDict):
    messages: Annotated[list[Any], add_messages]


def _make_request(*, compaction_enabled: bool = True):
    return BasicLLMRequest(
        max_steps=5,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
        compaction_enabled=compaction_enabled,
        compaction_max_token_threshold=100,
    )


def _make_mock_llm(responses):
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(side_effect=responses)
    return mock_llm


def _build_history(*, include_recent_tool_pair: bool = False) -> list[Any]:
    messages: list[Any] = [HumanMessage(content="seed")]
    for idx in range(12):
        messages.append(HumanMessage(content=f"history-{idx}-" + ("x" * 40)))
        messages.append(AIMessage(content=f"reply-{idx}"))
    if include_recent_tool_pair:
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "search_tool", "args": {"query": "recent"}, "id": "recent-1"}],
                ),
                ToolMessage(content="recent-result", tool_call_id="recent-1"),
            ]
        )
    return messages


async def _build_and_run(
    *,
    request,
    messages,
    tools,
    llm_responses,
    prepare_step_hook=None,
):
    node_builder = ToolsNodes()
    node_builder.tools = tools
    mock_llm = _make_mock_llm(llm_responses)
    node_builder.get_llm_client = lambda *a, **kw: mock_llm

    if prepare_step_hook is not None:
        request.prepare_step_hooks = [prepare_step_hook]

    graph_builder = StateGraph(AgentState)
    entry = await node_builder.build_react_nodes(
        graph_builder=graph_builder,
        composite_node_name="test_react",
    )
    graph_builder.set_entry_point(entry)
    compiled = graph_builder.compile()

    config = {
        "configurable": {
            "graph_request": request,
            "trace_id": "test",
            "execution_id": "",
        }
    }

    with patch(
        "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
        return_value="You are a test assistant.",
    ):
        result = await compiled.ainvoke({"messages": messages}, config=config)

    return result["messages"] if isinstance(result, dict) else result


class TestCompactionInReactLoop:
    @pytest.mark.asyncio
    async def test_compaction_triggered_after_long_history(self):
        request = _make_request(compaction_enabled=True)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(),
                tools=[search_tool],
                llm_responses=[
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}],
                    ),
                    AIMessage(content="done"),
                ],
            )

        assert mock_compact.await_count >= 1
        assert isinstance(messages[-1], AIMessage)
        assert messages[-1].content == "done"

    @pytest.mark.asyncio
    async def test_agent_continues_after_compaction(self):
        request = _make_request(compaction_enabled=True)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(),
                tools=[search_tool],
                llm_responses=[
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}],
                    ),
                    AIMessage(content="done"),
                ],
            )

        assert mock_compact.await_count >= 1
        assert messages[-1].content == "done"
        assert any(isinstance(message, ToolMessage) for message in messages)

    @pytest.mark.asyncio
    async def test_recent_tool_pairs_preserved(self):
        request = _make_request(compaction_enabled=True)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(include_recent_tool_pair=True),
                tools=[search_tool],
                llm_responses=[AIMessage(content="done")],
            )

        assert mock_compact.await_count == 1
        assert any(isinstance(message, AIMessage) and message.tool_calls and message.tool_calls[0]["id"] == "recent-1" for message in messages)
        assert any(isinstance(message, ToolMessage) and message.tool_call_id == "recent-1" for message in messages)


class TestCompactionDisabled:
    @pytest.mark.asyncio
    async def test_no_compaction_when_disabled(self):
        request = _make_request(compaction_enabled=False)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(),
                tools=[search_tool],
                llm_responses=[
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}],
                    ),
                    AIMessage(content="done"),
                ],
            )

        assert mock_compact.await_count == 0
        assert messages[-1].content == "done"

    @pytest.mark.asyncio
    async def test_no_compaction_without_tools(self):
        request = _make_request(compaction_enabled=True)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(),
                tools=[],
                llm_responses=[AIMessage(content="done")],
            )

        assert mock_compact.await_count == 0
        assert messages[-1].content == "done"


class TestCompactionWithPrepareStep:
    @pytest.mark.asyncio
    async def test_prepare_step_then_compaction(self):
        request = _make_request(compaction_enabled=True)
        mock_compact = AsyncMock(side_effect=lambda messages, llm, config, model_name: messages)
        prepare_called = False

        async def prepare_step_hook(context: PrepareStepContext) -> PrepareStepResult:
            nonlocal prepare_called
            prepare_called = True
            modified_messages = list(context.messages) + [HumanMessage(content="prepared")]
            return PrepareStepResult(messages=modified_messages)

        with patch("apps.opspilot.metis.llm.chain.node.compact_messages", mock_compact):
            messages = await _build_and_run(
                request=request,
                messages=_build_history(),
                tools=[search_tool],
                llm_responses=[
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search_tool", "args": {"query": "test"}, "id": "tc1"}],
                    ),
                    AIMessage(content="done"),
                ],
                prepare_step_hook=prepare_step_hook,
            )

        assert prepare_called is True
        assert mock_compact.await_count >= 1
        assert messages[-1].content == "done"
