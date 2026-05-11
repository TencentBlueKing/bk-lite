"""
E2E tests: same entry node, different messages -> different intents -> different agents.

Verifies that from a single entry point, varying user messages cause the
intent classifier to return different intents, routing to different
downstream agent nodes.

The LLM call is mocked with a side_effect that maps input messages to
intents dynamically, simulating real intent classification behavior.
"""

import pytest

from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTRY_NODE_ID = "openai-1777450801989"

# Each tuple: (user_message, expected_intent, expected_agent_id)
MESSAGE_INTENT_AGENT = [
    ("帮我写一个Python监控脚本", "generate_script", "agents-1773989553282"),
    ("总结一下这个工单的内容", "summary_ticket", "agents-1773989974128"),
    ("从日志中提取错误信息", "ai_log_extraction", "agents-1773989998398"),
    ("检查这个脚本有没有问题", "scripts_check", "agents-1773990036863"),
    ("参考这个模板写一篇文档", "write_by_example", "agents-1773990058488"),
    ("整理一下这段内容的格式", "tidy_content", "agents-1773990420050"),
    ("把这段话改成正式的语气", "change_tone", "agents-1773990895494"),
    ("调整一下这篇文章的结构", "essay_adjust_content", "agents-1773990915824"),
    ("分析一下这段错误日志", "wrong_log_analysis", "agents-1773990933233"),
    ("检查一下这份日志有没有异常", "ai_log_check", "agents-1773990964763"),
]

# Build a lookup: message -> intent
_MSG_TO_INTENT = {msg: intent for msg, intent, _ in MESSAGE_INTENT_AGENT}


# ---------------------------------------------------------------------------
# Fake executor
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
# Dynamic mock: returns intent based on input message
# ---------------------------------------------------------------------------


def _dynamic_invoke_chat(params, *args, **kwargs):
    """Side effect for ChatService.invoke_chat that maps message to intent."""
    user_message = params.get("user_message", "")
    intent = _MSG_TO_INTENT.get(user_message, "unknown")
    return ({"message": intent}, {}, {})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_dynamic(workflow, mocker):
    """Create engine with dynamic intent mock (message-dependent)."""
    engine = create_chat_flow_engine(workflow, ENTRY_NODE_ID)

    mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
        side_effect=_dynamic_invoke_chat,
    )

    recorder = RecordingAgentExecutor(engine.variable_manager)
    engine.custom_node_executors["agents"] = recorder

    return engine, recorder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestSameEntryDifferentMessages:
    """Same entry node, different messages -> different agents."""

    @pytest.mark.parametrize(
        "user_message,expected_intent,expected_agent_id",
        MESSAGE_INTENT_AGENT,
        ids=[t[1] for t in MESSAGE_INTENT_AGENT],
    )
    def test_message_routes_to_correct_agent(self, intent_workflow, mocker, user_message, expected_intent, expected_agent_id):
        engine, recorder = _make_engine_dynamic(intent_workflow, mocker)

        engine.execute(
            {
                "last_message": user_message,
                "user_id": "tester@test.com",
                "node_id": ENTRY_NODE_ID,
            }
        )

        assert len(recorder.calls) == 1, f"message='{user_message}': expected 1 agent call, got {len(recorder.calls)}"
        assert recorder.calls[0]["node_id"] == expected_agent_id, (
            f"message='{user_message}' (intent={expected_intent}): " f"expected {expected_agent_id}, got {recorder.calls[0]['node_id']}"
        )


@pytest.mark.django_db(transaction=True)
class TestSequentialDifferentIntents:
    """Two different messages sent sequentially from the same entry."""

    def test_two_messages_route_to_different_agents(self, intent_workflow, mocker):
        """Send two messages with different intents, verify each goes to its own agent."""
        msg_a, intent_a, agent_a = MESSAGE_INTENT_AGENT[0]  # generate_script
        msg_b, intent_b, agent_b = MESSAGE_INTENT_AGENT[1]  # summary_ticket

        # First message
        engine_1, recorder_1 = _make_engine_dynamic(intent_workflow, mocker)
        engine_1.execute(
            {
                "last_message": msg_a,
                "user_id": "tester@test.com",
                "node_id": ENTRY_NODE_ID,
            }
        )

        # Second message (new engine instance, same workflow)
        engine_2, recorder_2 = _make_engine_dynamic(intent_workflow, mocker)
        engine_2.execute(
            {
                "last_message": msg_b,
                "user_id": "tester@test.com",
                "node_id": ENTRY_NODE_ID,
            }
        )

        assert recorder_1.calls[0]["node_id"] == agent_a, f"First message should route to {agent_a}"
        assert recorder_2.calls[0]["node_id"] == agent_b, f"Second message should route to {agent_b}"
        assert agent_a != agent_b, "Two different intents must route to different agents"


@pytest.mark.django_db(transaction=True)
class TestMessagePassthrough:
    """Verify the downstream agent receives the original user message."""

    @pytest.mark.parametrize(
        "user_message,expected_intent,expected_agent_id",
        MESSAGE_INTENT_AGENT[:3],
        ids=[t[1] for t in MESSAGE_INTENT_AGENT[:3]],
    )
    def test_agent_receives_original_message(self, intent_workflow, mocker, user_message, expected_intent, expected_agent_id):
        engine, recorder = _make_engine_dynamic(intent_workflow, mocker)

        engine.execute(
            {
                "last_message": user_message,
                "user_id": "tester@test.com",
                "node_id": ENTRY_NODE_ID,
            }
        )

        assert len(recorder.calls) == 1
        assert recorder.calls[0]["input"] == user_message, f"Agent should receive '{user_message}', got '{recorder.calls[0]['input']}'"
