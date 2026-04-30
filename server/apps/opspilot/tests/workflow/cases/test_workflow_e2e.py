"""
E2E tests for the ChatFlowEngine workflow execution.

These tests exercise the full path:
  BotWorkFlow (DB) -> ChatFlowEngine -> node executors -> DB result records

Real database, fake node executors (no LLM calls).
"""

import pytest

from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory, WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

# ---------------------------------------------------------------------------
# Fake executor: replaces the real AgentNode so we never call an LLM.
# ---------------------------------------------------------------------------


class FakeAgentExecutor(BaseNodeExecutor):
    """Returns a deterministic response for testing."""

    def execute(self, node_id, node_config, input_data):
        # Echo back the input with a prefix so tests can verify data flow
        input_key = node_config.get("data", {}).get("config", {}).get("inputParams", "last_message")
        output_key = node_config.get("data", {}).get("config", {}).get("outputParams", "last_message")
        received = input_data.get(input_key, "")
        return {output_key: f"agent_processed: {received}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestWorkflowE2ESuccess:
    """Two-node workflow (entry -> agents) executes successfully end-to-end."""

    def test_two_node_workflow_produces_correct_result(self, bot_workflow):
        """Engine returns the agent-processed message."""
        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        # Inject fake executor for "agents" node type
        engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)

        result = engine.execute({"last_message": "hello world"})

        # The engine extracts the final `last_message` variable value
        # (not the dict wrapper) — see engine.py:1365
        assert result == "agent_processed: hello world"

    def test_two_node_workflow_creates_task_result_record(self, bot_workflow):
        """A WorkFlowTaskResult with status=SUCCESS is persisted."""
        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)

        engine.execute({"last_message": "hello world"})

        task_results = WorkFlowTaskResult.objects.filter(
            bot_work_flow=bot_workflow,
            execution_id=engine.execution_id,
        )
        assert task_results.count() == 1
        task_result = task_results.first()
        assert task_result.status == WorkFlowTaskStatus.SUCCESS

    def test_two_node_workflow_creates_node_result_records(self, bot_workflow):
        """Two WorkFlowTaskNodeResult records (entry + agent) are persisted."""
        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)

        engine.execute({"last_message": "hello world"})

        node_results = WorkFlowTaskNodeResult.objects.filter(
            execution_id=engine.execution_id,
        ).order_by("node_index")

        assert node_results.count() == 2

        entry_result = node_results[0]
        assert entry_result.node_id == "entry_node"
        assert entry_result.status == "completed"

        agent_result = node_results[1]
        assert agent_result.node_id == "agent_node"
        assert agent_result.status == "completed"

    def test_two_node_workflow_records_conversation_history(self, bot_workflow):
        """User input and bot output conversation records are persisted."""
        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)

        engine.execute(
            {
                "last_message": "hello world",
                "user_id": "tester@test.com",
                "node_id": "entry_node",
            }
        )

        histories = WorkFlowConversationHistory.objects.filter(
            execution_id=engine.execution_id,
        ).order_by("conversation_time")

        assert histories.count() == 2
        assert histories[0].conversation_role == "user"
        assert histories[0].conversation_content == "hello world"
        assert histories[1].conversation_role == "bot"
        assert "agent_processed" in histories[1].conversation_content

    def test_task_result_output_data_contains_execution_summary(self, bot_workflow):
        """The output_data summary tracks completed node counts."""
        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FakeAgentExecutor(engine.variable_manager)

        engine.execute({"last_message": "hello world"})

        task_result = WorkFlowTaskResult.objects.get(execution_id=engine.execution_id)
        summary = task_result.output_data.get("summary", {})

        assert summary["total_nodes"] == 2
        assert summary["completed_nodes"] == 2
        assert summary["failed_nodes"] == 0


@pytest.mark.django_db(transaction=True)
class TestWorkflowE2EFailure:
    """Workflow execution handles node failure correctly."""

    def test_agent_failure_produces_fail_status(self, bot_workflow):
        """When the agent node raises, task result status is FAIL."""

        class FailingAgentExecutor(BaseNodeExecutor):
            def execute(self, node_id, node_config, input_data):
                raise RuntimeError("LLM service unavailable")

        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FailingAgentExecutor(engine.variable_manager)

        result = engine.execute({"last_message": "hello world"})

        # Engine should return error info, not raise
        assert isinstance(result, dict)
        assert result.get("error") is not None or result.get("success") is False

        task_result = WorkFlowTaskResult.objects.get(execution_id=engine.execution_id)
        assert task_result.status == WorkFlowTaskStatus.FAIL

    def test_agent_failure_records_failed_node_in_summary(self, bot_workflow):
        """The output_data summary includes the failed node info."""

        class FailingAgentExecutor(BaseNodeExecutor):
            def execute(self, node_id, node_config, input_data):
                raise RuntimeError("LLM service unavailable")

        engine = create_chat_flow_engine(bot_workflow, "entry_node")
        engine.custom_node_executors["agents"] = FailingAgentExecutor(engine.variable_manager)

        engine.execute({"last_message": "hello world"})

        task_result = WorkFlowTaskResult.objects.get(execution_id=engine.execution_id)
        summary = task_result.output_data.get("summary", {})

        assert summary["failed_nodes"] >= 1
        failed_node = summary.get("failed_node")
        assert failed_node is not None
        assert failed_node["node_id"] == "agent_node"
