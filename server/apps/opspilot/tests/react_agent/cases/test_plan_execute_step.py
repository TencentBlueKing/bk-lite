"""
Tests for Plan-and-Execute step instruction injection fix.

Verifies:
- executor_node injects current step as HumanMessage into messages
- executor_node does NOT spread full state (avoids message duplication)
- executor_node with empty plan returns state unchanged
- HumanMessage contains the current step description
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

import asyncio  # noqa: E402

import pytest  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from apps.opspilot.metis.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentNode, PlanAndExecuteAgentRequest  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def node():
    n = PlanAndExecuteAgentNode()
    return n


@pytest.fixture
def config():
    req = PlanAndExecuteAgentRequest(
        openai_api_base="http://localhost:8000/v1",
        openai_api_key="test-key",
        model="gpt-4o",
        user_message="查看K8s集群状态",
    )
    return {"configurable": {"graph_request": req}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutorNodeStepInjection:
    """Tests for executor_node injecting step instruction into messages."""

    def test_injects_human_message_with_step(self, node, config):
        """executor_node should add a HumanMessage with the current step."""
        state = {
            "current_plan": ["获取K8s集群信息", "列出所有节点", "统计Pod数量"],
            "original_plan": ["获取K8s集群信息", "列出所有节点", "统计Pod数量"],
            "messages": [AIMessage(content="计划已制定")],
            "execution_prompt": None,
            "final_response": None,
        }

        result = asyncio.run(node.executor_node(state, config))

        # Should have messages with a HumanMessage
        assert "messages" in result
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert isinstance(msg, HumanMessage)
        assert "获取K8s集群信息" in msg.content

    def test_does_not_spread_full_state(self, node, config):
        """executor_node should NOT return the full state (no **state spread)."""
        state = {
            "current_plan": ["步骤1"],
            "original_plan": ["步骤1"],
            "messages": [AIMessage(content="existing msg 1"), AIMessage(content="existing msg 2")],
            "execution_prompt": None,
            "final_response": None,
        }

        result = asyncio.run(node.executor_node(state, config))

        # Should only contain execution_prompt and messages keys
        # Should NOT contain original_plan, current_plan, final_response
        # (those are not updated by executor_node)
        assert "original_plan" not in result
        assert "current_plan" not in result
        assert "final_response" not in result

        # messages should only contain the new HumanMessage, not the old ones
        assert len(result["messages"]) == 1

    def test_empty_plan_returns_state_unchanged(self, node, config):
        """executor_node with empty plan should return state as-is."""
        state = {
            "current_plan": [],
            "original_plan": ["步骤1"],
            "messages": [],
            "execution_prompt": None,
            "final_response": None,
        }

        result = asyncio.run(node.executor_node(state, config))

        # Empty plan — no new messages, returns state spread
        assert "messages" not in result or len(result.get("messages", [])) == 0

    def test_step_instruction_contains_user_message(self, node, config):
        """The injected step instruction should reference the original user task."""
        state = {
            "current_plan": ["列出所有节点"],
            "original_plan": ["列出所有节点"],
            "messages": [],
            "execution_prompt": None,
            "final_response": None,
        }

        result = asyncio.run(node.executor_node(state, config))

        msg = result["messages"][0]
        # Should contain both the step and the original user message
        assert "列出所有节点" in msg.content
        assert "查看K8s集群状态" in msg.content

    def test_execution_prompt_field_is_set(self, node, config):
        """execution_prompt field should still be set in the return."""
        state = {
            "current_plan": ["检查Pod状态"],
            "original_plan": ["检查Pod状态"],
            "messages": [],
            "execution_prompt": None,
            "final_response": None,
        }

        result = asyncio.run(node.executor_node(state, config))

        assert "execution_prompt" in result
        assert "检查Pod状态" in result["execution_prompt"]
