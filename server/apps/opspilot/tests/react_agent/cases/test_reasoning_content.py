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

import pytest  # type: ignore[import-not-found]  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.graph import StateGraph, add_messages  # noqa: E402

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, ReflectionConfig, RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes, _patched_convert_message_to_dict  # noqa: E402


@tool
def search_tool(q: str) -> str:
    """Search for information."""
    return f"found:{q}"


class AgentState(TypedDict):
    messages: Annotated[list[Any], add_messages]


def _make_request(*, model: str):
    return BasicLLMRequest(
        model=model,
        max_steps=5,
        compaction_enabled=False,
        retry_config=RetryConfig(enabled=False),
        reflection_config=ReflectionConfig(enabled=False),
        timeout_config=TimeoutConfig(enabled=False),
    )


def _make_mock_llm(responses):
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(side_effect=responses)
    return mock_llm


async def _build_and_run(*, request, messages, tools, llm_responses):
    node_builder = ToolsNodes()
    node_builder.tools = tools
    mock_llm = _make_mock_llm(llm_responses)
    node_builder.get_llm_client = lambda *a, **kw: mock_llm

    graph_builder: Any = StateGraph(AgentState)
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


class TestReasoningContentPreserved:
    @pytest.mark.asyncio
    async def test_reasoning_content_serialized(self):
        msg = AIMessage(content="hello", additional_kwargs={"reasoning_content": "I think..."})
        result = _patched_convert_message_to_dict(msg)

        assert result["reasoning_content"] == "I think..."

    @pytest.mark.asyncio
    async def test_no_reasoning_content_no_effect(self):
        msg = AIMessage(content="hello")
        result = _patched_convert_message_to_dict(msg)

        assert "reasoning_content" not in result

    @pytest.mark.asyncio
    async def test_reasoning_content_with_tool_calls(self):
        msg = AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "thinking"},
            tool_calls=[{"name": "search", "args": {"q": "test"}, "id": "tc1"}],
        )
        result = _patched_convert_message_to_dict(msg)

        assert result["reasoning_content"] == "thinking"
        assert result["tool_calls"]
        assert result["tool_calls"][0]["id"] == "tc1"

    @pytest.mark.asyncio
    async def test_other_message_types_unaffected(self):
        messages = [
            HumanMessage(content="hello"),
            SystemMessage(content="system"),
            ToolMessage(content="tool", tool_call_id="tc1"),
        ]

        for msg in messages:
            result = _patched_convert_message_to_dict(msg)
            assert "reasoning_content" not in result


class TestReasoningContentInReactLoop:
    @pytest.mark.asyncio
    async def test_deepseek_multi_round_tool_call(self):
        request = _make_request(model="deepseek-chat")
        messages = await _build_and_run(
            request=request,
            messages=[HumanMessage(content="search stuff")],
            tools=[search_tool],
            llm_responses=[
                AIMessage(
                    content="",
                    additional_kwargs={"reasoning_content": "let me think..."},
                    tool_calls=[{"name": "search_tool", "args": {"q": "test"}, "id": "tc1"}],
                ),
                AIMessage(content="done"),
            ],
        )

        assert isinstance(messages[-1], AIMessage)
        assert messages[-1].content == "done"

    @pytest.mark.asyncio
    async def test_qwen_multi_round_tool_call(self):
        request = _make_request(model="qwen-chat")
        messages = await _build_and_run(
            request=request,
            messages=[HumanMessage(content="search stuff")],
            tools=[search_tool],
            llm_responses=[
                AIMessage(
                    content="",
                    additional_kwargs={"reasoning_content": "let me think..."},
                    tool_calls=[{"name": "search_tool", "args": {"q": "test"}, "id": "tc1"}],
                ),
                AIMessage(content="done"),
            ],
        )

        assert isinstance(messages[-1], AIMessage)
        assert messages[-1].content == "done"
