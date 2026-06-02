"""
Tests for User Choice Tool (LLM-driven tool approach).

The `request_user_choice` tool is built by `_build_choice_tool()` and
injected into the ReAct tool list. The LLM autonomously calls it when it
needs the user to select from multiple options. The tool dispatches an SSE
event, polls Redis for the selection, and returns a text result the LLM
uses to proceed.

Verifies:
- Tool is injected when tools exist
- User selection → returns selection text
- Timeout → returns default selection text
- SSE event dispatched with correct fields
- Unattended mode → auto-selects immediately
"""

import json
import sys
import types
from types import SimpleNamespace

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

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest  # noqa: E402
from apps.opspilot.metis.llm.chain.entity import ReflectionConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.entity import RetryConfig, TimeoutConfig  # noqa: E402
from apps.opspilot.metis.llm.chain.node import ToolsNodes  # noqa: E402


@pytest.fixture
def settings():
    return SimpleNamespace(MIDDLEWARE=(), CACHES={})


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool
def query_table(table_name: str) -> str:
    """Query a database table."""
    return f"queried: {table_name}"


@tool
def safe_tool(query: str) -> str:
    """A safe tool that never needs choice."""
    return f"safe: {query}"


@tool
def analyze_deployment_configurations() -> str:
    """Return a K8s config-analysis payload with issues."""
    return json.dumps(
        {
            "cluster_name": "Kubernetes - 1",
            "problematic": 32,
            "issues_detail": [
                {
                    "severity": "high",
                    "issue": "未配置存活探针",
                    "count": 10,
                    "workloads": ["nginx-test (default)"],
                }
            ],
            "_deployments_full": [
                {
                    "name": "nginx-test",
                    "namespace": "default",
                    "issues": ["未配置存活探针"],
                    "config_analysis": {"containers": []},
                }
            ],
        },
        ensure_ascii=False,
    )


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
    mock_choice_result=None,
    trigger_type="interactive",
):
    """Build ReAct graph with mocked choice tool.

    The LLM mock returns pre-defined responses. When one of them includes
    a tool_call to `request_user_choice`, the tool executes, dispatches
    an event, and polls Redis (mocked via `wait_for_choice`).
    """
    if tools_list is None:
        tools_list = [query_table, safe_tool]

    node_builder = ToolsNodes()
    node_builder.tools = tools_list

    call_count = {"n": 0}
    responses = list(mock_llm_responses)
    choice_events = []

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
            "execution_id": "exec-choice-test",
            "node_id": "node-1",
            "trigger_type": trigger_type,
        }
    }

    async def mock_wait_for_choice(execution_id, node_id, choice_id, options, default_keys, **kwargs):
        if callable(mock_choice_result):
            return mock_choice_result(execution_id, node_id, choice_id, options, default_keys)
        return mock_choice_result or {"selected": [options[0]["key"]], "source": "user"}

    def capture_event(name, data):
        if name == "user_choice_request":
            choice_events.append(dict(data))

    with (
        patch(
            "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
            return_value="You are a test assistant.",
        ),
        patch(
            "apps.opspilot.metis.llm.chain.node.wait_for_choice",
            side_effect=mock_wait_for_choice,
        ),
        patch(
            "apps.opspilot.metis.llm.chain.node.is_interrupt_requested_async",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "apps.opspilot.metis.llm.chain.node.dispatch_custom_event",
            side_effect=capture_event,
        ),
    ):
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="test")]},
            config=config,
        )

    return result.get("messages", []), call_count["n"], choice_events


# ---------------------------------------------------------------------------
# Tests: Tool injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestChoiceToolInjection:
    """request_user_choice tool is injected when tools exist."""

    async def test_choice_tool_present(self):
        """The choice tool is built and added to tools list."""
        node_builder = ToolsNodes()
        node_builder.tools = [query_table]
        choice_tool = node_builder._build_choice_tool()
        assert choice_tool is not None
        assert choice_tool.name == "request_user_choice"

    async def test_no_choice_tool_without_tools(self):
        """No choice tool when there are no tools."""
        node_builder = ToolsNodes()
        node_builder.tools = []
        choice_tool = node_builder._build_choice_tool() if node_builder.tools else None
        assert choice_tool is None


# ---------------------------------------------------------------------------
# Tests: User Selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUserSelection:
    """LLM calls request_user_choice → user selects → proceeds."""

    async def test_user_selects_then_executes(self):
        """LLM asks for choice, user selects, then calls the actual tool."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            # Step 1: LLM calls request_user_choice
            AIMessage(
                content="Let me ask which table to query.",
                tool_calls=[
                    {
                        "name": "request_user_choice",
                        "args": {
                            "title": "请选择要查询的表",
                            "options": [
                                {"key": "users", "label": "用户表", "description": "用户信息"},
                                {"key": "orders", "label": "订单表", "description": "订单信息"},
                            ],
                            "description": "请选择一个表进行查询",
                            "multiple": False,
                        },
                        "id": "c_choice",
                    }
                ],
            ),
            # Step 2: After selection, LLM calls the actual tool
            AIMessage(
                content="User selected, proceeding.",
                tool_calls=[
                    {
                        "name": "query_table",
                        "args": {"table_name": "users"},
                        "id": "c_exec",
                    }
                ],
            ),
            # Step 3: Done
            AIMessage(content="Query completed."),
        ]

        messages, llm_calls, choice_events = await _build_and_run(
            request,
            responses,
            mock_choice_result={"selected": ["users"], "source": "user"},
        )

        assert llm_calls == 3
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Choice tool returned selection text
        assert any("用户选择了" in str(m.content) for m in tool_msgs)
        # Actual tool executed
        assert any("queried: users" in str(m.content) for m in tool_msgs)
        # SSE event dispatched
        assert len(choice_events) >= 1

    async def test_k8s_plain_text_repair_prompt_becomes_standard_choice_tool(self):
        """K8s repair-mode follow-up should synthesize a proper choice tool instead of showing plain text options."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="先做配置检查。",
                tool_calls=[
                    {
                        "name": "analyze_deployment_configurations",
                        "args": {},
                        "id": "c_analysis",
                    }
                ],
            ),
            AIMessage(
                content=(
                    "配置检查报告 - Kubernetes - 1 集群\n"
                    "## 高危问题\n"
                    "1. 未配置存活探针\n"
                    "共识别到 32 个工作负载存在问题，请选择修复展示方式：\n"
                    "1. 按问题类别聚合\n"
                    "2. 按工作负载聚合\n"
                    "3. 全部一次性展示"
                )
            ),
            AIMessage(
                content="用户已选择，生成修复对比。",
                tool_calls=[
                    {
                        "name": "generate_repair_report",
                        "args": {
                            "title": "K8S 配置修复对比",
                            "group_by": "target",
                            "expected_target_count": 1,
                        },
                        "id": "c_repair",
                    }
                ],
            ),
            AIMessage(content="修复对比已生成。"),
        ]

        messages, llm_calls, choice_events = await _build_and_run(
            request,
            responses,
            tools_list=[analyze_deployment_configurations],
            mock_choice_result={"selected": ["按工作负载聚合"], "source": "user"},
        )

        assert llm_calls == 4
        assert len(choice_events) == 1
        assert choice_events[0]["title"] == "请选择修复展示方式"
        assert [option["label"] for option in choice_events[0]["options"]] == [
            "按问题类别聚合",
            "按工作负载聚合",
            "全部一次性展示",
        ]

        synthetic_choice_ai = next(
            m
            for m in messages
            if isinstance(m, AIMessage) and any(tc.get("name") == "request_user_choice" for tc in (m.tool_calls or []))
        )
        assert str(synthetic_choice_ai.content).strip() == ""

    async def test_k8s_analysis_dispatches_report_and_skips_llm_before_choice(self):
        """After K8s analysis with issues, backend should emit a single structured report and go directly to choice."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        node_builder = ToolsNodes()
        node_builder.tools = [analyze_deployment_configurations]

        responses = [
            AIMessage(
                content="先做配置检查。",
                tool_calls=[
                    {
                        "name": "analyze_deployment_configurations",
                        "args": {},
                        "id": "c_analysis",
                    }
                ],
            ),
            AIMessage(
                content="用户已选择，生成修复对比。",
                tool_calls=[
                    {
                        "name": "generate_repair_report",
                        "args": {
                            "title": "K8S 配置修复对比",
                            "group_by": "target",
                            "expected_target_count": 1,
                        },
                        "id": "c_repair",
                    }
                ],
            ),
            AIMessage(content="修复对比已生成。"),
        ]

        call_count = {"n": 0}
        captured_events = []

        async def mock_ainvoke(messages, *args, **kwargs):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            if idx == 1:
                has_choice_result = any(
                    getattr(message, "type", "") == "tool" and getattr(message, "name", "") == "request_user_choice"
                    for message in messages
                )
                assert has_choice_result, "LLM should not be called again before request_user_choice completes"
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
                "execution_id": "exec-choice-test",
                "node_id": "node-1",
                "trigger_type": "interactive",
            }
        }

        async def mock_wait_for_choice(execution_id, node_id, choice_id, options, default_keys, **kwargs):
            return {"selected": ["按工作负载聚合"], "source": "user"}

        def capture_event(name, data):
            captured_events.append((name, dict(data)))

        with (
            patch(
                "apps.opspilot.metis.llm.chain.node.TemplateLoader.render_template",
                return_value="You are a test assistant.",
            ),
            patch(
                "apps.opspilot.metis.llm.chain.node.wait_for_choice",
                side_effect=mock_wait_for_choice,
            ),
            patch(
                "apps.opspilot.metis.llm.chain.node.is_interrupt_requested_async",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "apps.opspilot.metis.llm.chain.node.dispatch_custom_event",
                side_effect=capture_event,
            ),
        ):
            await graph.ainvoke(
                {"messages": [HumanMessage(content="test")]},
                config=config,
            )

        event_names = [name for name, _data in captured_events]
        assert "config_analysis_report" in event_names
        assert "user_choice_request" in event_names
        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# Tests: Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestChoiceTimeout:
    """LLM calls request_user_choice → timeout → uses default."""

    async def test_timeout_uses_default(self):
        """LLM asks for choice, times out, uses default option."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            # Step 1: LLM calls request_user_choice
            AIMessage(
                content="Asking user to choose.",
                tool_calls=[
                    {
                        "name": "request_user_choice",
                        "args": {
                            "title": "选择操作",
                            "options": [
                                {"key": "opt_a", "label": "选项A"},
                                {"key": "opt_b", "label": "选项B"},
                            ],
                            "default_keys": ["opt_a"],
                        },
                        "id": "c_choice",
                    }
                ],
            ),
            # Step 2: After timeout, LLM proceeds with default
            AIMessage(content="Using default option."),
        ]

        messages, llm_calls, _ = await _build_and_run(
            request,
            responses,
            mock_choice_result={"selected": ["opt_a"], "source": "timeout"},
        )

        # LLM calls: Step 1 + forced tool_choice='any' after choice tool + Step 2
        assert llm_calls == 3
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Choice tool returned timeout text
        assert any("默认选项" in str(m.content) or "未在规定时间" in str(m.content) for m in tool_msgs)


# ---------------------------------------------------------------------------
# Tests: SSE Event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestChoiceSSEEvent:
    """SSE event is dispatched with correct fields."""

    async def test_sse_event_fields(self):
        """SSE event contains all required fields."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="Asking for choice.",
                tool_calls=[
                    {
                        "name": "request_user_choice",
                        "args": {
                            "title": "测试选择",
                            "options": [
                                {"key": "k1", "label": "Label 1", "recommended": True},
                                {"key": "k2", "label": "Label 2"},
                            ],
                            "description": "测试描述",
                            "multiple": True,
                            "default_keys": ["k1"],
                        },
                        "id": "c_choice",
                    }
                ],
            ),
            AIMessage(content="Done."),
        ]

        _, _, choice_events = await _build_and_run(
            request,
            responses,
            mock_choice_result={"selected": ["k1"], "source": "user"},
        )

        assert len(choice_events) >= 1
        event = choice_events[0]

        # Required fields
        assert "execution_id" in event
        assert "node_id" in event
        assert "choice_id" in event
        assert "title" in event
        assert "options" in event
        assert "multiple" in event
        assert "timeout_seconds" in event
        assert "default_keys" in event
        assert "display_hint" in event

        # Values
        assert event["title"] == "测试选择"
        assert event["description"] == "测试描述"
        assert event["multiple"] is True
        assert len(event["options"]) == 2
        assert event["options"][0]["key"] == "k1"
        assert event["options"][0]["recommended"] is True


# ---------------------------------------------------------------------------
# Tests: Unattended Mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUnattendedMode:
    """Unattended mode auto-selects without waiting."""

    async def test_unattended_auto_selects(self):
        """In unattended mode, choice is auto-resolved immediately."""
        request = BasicLLMRequest(
            max_steps=10,
            compaction_enabled=False,
            retry_config=RetryConfig(enabled=False),
            reflection_config=ReflectionConfig(enabled=False),
            timeout_config=TimeoutConfig(enabled=False),
        )

        responses = [
            AIMessage(
                content="Asking for choice.",
                tool_calls=[
                    {
                        "name": "request_user_choice",
                        "args": {
                            "title": "选择",
                            "options": [
                                {"key": "auto_opt", "label": "自动选项"},
                            ],
                            "default_keys": ["auto_opt"],
                        },
                        "id": "c_choice",
                    }
                ],
            ),
            AIMessage(content="Auto-selected."),
        ]

        messages, llm_calls, _ = await _build_and_run(
            request,
            responses,
            mock_choice_result={"selected": ["auto_opt"], "source": "auto"},
            trigger_type="unattended",
        )

        assert llm_calls == 3  # 3 calls: initial + forced tool_choice='any' after choice + final
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        # Choice tool returned auto-select text
        assert any("自动选择" in str(m.content) for m in tool_msgs)
