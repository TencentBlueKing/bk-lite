"""
E2E tests for intent-classification workflow routing.

Uses BotWorkFlow id=4 from the local database (real flow_json).
Tests that the same user message routed through different entry nodes
goes through intent classification and reaches the correct downstream
agent node.

The LLM call inside IntentClassifierNode is mocked so we control
which intent is returned; the agent nodes use a fake executor.
"""

import pytest

from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models.bot_mgmt import WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

# ---------------------------------------------------------------------------
# All entry node IDs present in BotWorkFlow id=4
# ---------------------------------------------------------------------------
ENTRY_NODES = {
    "agui": "agui-1770117632918",
    "restful": "restful-1774000290890",
    "openai": "openai-1777450801989",
    "celery": "celery-1777450797864",
    "web_chat": "web_chat-1777450807494",
}

INTENT_NODE_ID = "intent_classification-1773989472700"

# Mapping: intent name -> target agent node id (from edge sourceHandle)
INTENT_TO_AGENT = {
    "generate_script": "agents-1773989553282",
    "summary_ticket": "agents-1773989974128",
    "ai_log_extraction": "agents-1773989998398",
    "scripts_check": "agents-1773990036863",
    "write_by_example": "agents-1773990058488",
    "tidy_content": "agents-1773990420050",
    "change_tone": "agents-1773990895494",
    "essay_adjust_content": "agents-1773990915824",
    "wrong_log_analysis": "agents-1773990933233",
    "ai_log_check": "agents-1773990964763",
}


# ---------------------------------------------------------------------------
# Fake executor that records which agent node was invoked
# ---------------------------------------------------------------------------


class RecordingAgentExecutor(BaseNodeExecutor):
    """Records calls so tests can verify which agent was routed to."""

    def __init__(self, variable_manager):
        super().__init__(variable_manager)
        self.calls = []

    def execute(self, node_id, node_config, input_data):
        input_key = node_config.get("data", {}).get("config", {}).get("inputParams", "last_message")
        output_key = node_config.get("data", {}).get("config", {}).get("outputParams", "last_message")
        received = input_data.get(input_key, "")
        self.calls.append({"node_id": node_id, "input": received})
        return {output_key: f"handled_by:{node_id}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(workflow, entry_node_id, mocker, forced_intent):
    """Create a ChatFlowEngine with mocked intent classification and fake agent."""
    engine = create_chat_flow_engine(workflow, entry_node_id)

    # Mock the LLM call inside IntentClassifierNode to return our forced intent
    mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
        return_value=({"message": forced_intent}, {}, {}),
    )

    # Replace all agent executors with our recording executor
    recorder = RecordingAgentExecutor(engine.variable_manager)
    engine.custom_node_executors["agents"] = recorder

    return engine, recorder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestIntentRoutingPerEntryNode:
    """Same message + same forced intent -> same agent, regardless of entry node."""

    @pytest.mark.parametrize("entry_label,entry_node_id", list(ENTRY_NODES.items()))
    @pytest.mark.parametrize(
        "forced_intent,expected_agent_id",
        [
            ("generate_script", "agents-1773989553282"),
            ("summary_ticket", "agents-1773989974128"),
            ("wrong_log_analysis", "agents-1773990933233"),
        ],
    )
    def test_same_intent_routes_to_same_agent_for_all_entries(
        self, intent_workflow, mocker, entry_label, entry_node_id, forced_intent, expected_agent_id
    ):
        """For a given forced intent, every entry node should route to the same agent."""
        engine, recorder = _make_engine(intent_workflow, entry_node_id, mocker, forced_intent)

        engine.execute(
            {
                "last_message": "帮我写一个Python脚本",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        # Verify the correct agent was called
        assert len(recorder.calls) == 1, (
            f"Expected exactly 1 agent call for entry={entry_label}, intent={forced_intent}, " f"got {len(recorder.calls)}: {recorder.calls}"
        )
        assert recorder.calls[0]["node_id"] == expected_agent_id, (
            f"entry={entry_label}, intent={forced_intent}: " f"expected agent {expected_agent_id}, got {recorder.calls[0]['node_id']}"
        )

    @pytest.mark.parametrize("entry_label,entry_node_id", list(ENTRY_NODES.items()))
    def test_intent_node_receives_user_message(self, intent_workflow, mocker, entry_label, entry_node_id):
        """The intent classifier receives the original user message from any entry."""
        invoke_chat = mocker.patch(
            "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
            return_value=({"message": "generate_script"}, {}, {}),
        )

        engine = create_chat_flow_engine(intent_workflow, entry_node_id)
        recorder = RecordingAgentExecutor(engine.variable_manager)
        engine.custom_node_executors["agents"] = recorder

        engine.execute(
            {
                "last_message": "请生成一个监控脚本",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        # ChatService.invoke_chat should have been called with our message
        invoke_chat.assert_called_once()
        call_params = invoke_chat.call_args[0][0]
        assert call_params["user_message"] == "请生成一个监控脚本", f"entry={entry_label}: intent classifier did not receive the original message"


@pytest.mark.django_db(transaction=True)
class TestIntentRoutingAllIntents:
    """Verify every configured intent routes to its correct agent."""

    @pytest.mark.parametrize("forced_intent,expected_agent_id", list(INTENT_TO_AGENT.items()))
    def test_each_intent_routes_correctly(self, intent_workflow, mocker, forced_intent, expected_agent_id):
        """Each intent in the flow_json routes to the expected agent node."""
        entry_node_id = ENTRY_NODES["openai"]  # Use openai as representative entry
        engine, recorder = _make_engine(intent_workflow, entry_node_id, mocker, forced_intent)

        engine.execute(
            {
                "last_message": "测试消息",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        assert len(recorder.calls) == 1, f"intent={forced_intent}: expected 1 agent call, got {len(recorder.calls)}"
        assert (
            recorder.calls[0]["node_id"] == expected_agent_id
        ), f"intent={forced_intent}: expected {expected_agent_id}, got {recorder.calls[0]['node_id']}"


@pytest.mark.django_db(transaction=True)
class TestIntentRoutingDbRecords:
    """Verify database records are correct after intent-routed execution."""

    def test_task_result_is_success(self, intent_workflow, mocker):
        """Successful intent routing produces SUCCESS task result."""
        entry_node_id = ENTRY_NODES["openai"]
        engine, _ = _make_engine(intent_workflow, entry_node_id, mocker, "generate_script")

        engine.execute(
            {
                "last_message": "写个脚本",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        task_result = WorkFlowTaskResult.objects.get(execution_id=engine.execution_id)
        assert task_result.status == WorkFlowTaskStatus.SUCCESS

    def test_node_results_include_entry_intent_and_agent(self, intent_workflow, mocker):
        """Three node results: entry, intent_classification, agent."""
        entry_node_id = ENTRY_NODES["openai"]
        engine, _ = _make_engine(intent_workflow, entry_node_id, mocker, "generate_script")

        engine.execute(
            {
                "last_message": "写个脚本",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        node_results = WorkFlowTaskNodeResult.objects.filter(
            execution_id=engine.execution_id,
        ).order_by("node_index")

        node_ids = [nr.node_id for nr in node_results]
        assert entry_node_id in node_ids, f"Entry node {entry_node_id} not in results"
        assert INTENT_NODE_ID in node_ids, "Intent classification node not in results"
        assert "agents-1773989553282" in node_ids, "Target agent node not in results"

        # All should be completed
        for nr in node_results:
            assert nr.status == "completed", f"Node {nr.node_id} status={nr.status}, expected completed"

    def test_agent_receives_original_message_not_intent_label(self, intent_workflow, mocker):
        """The downstream agent should receive the user's original message, not the intent label."""
        entry_node_id = ENTRY_NODES["openai"]
        engine, recorder = _make_engine(intent_workflow, entry_node_id, mocker, "generate_script")

        engine.execute(
            {
                "last_message": "帮我写一个清理临时文件的Shell脚本",
                "user_id": "tester@test.com",
                "node_id": entry_node_id,
            }
        )

        assert len(recorder.calls) == 1
        # The agent should get the original user message, not "generate_script"
        assert recorder.calls[0]["input"] == "帮我写一个清理临时文件的Shell脚本", f"Agent received '{recorder.calls[0]['input']}' instead of the original message"
