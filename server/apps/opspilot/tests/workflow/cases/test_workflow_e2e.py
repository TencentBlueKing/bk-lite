"""
E2E tests for the ChatFlowEngine workflow execution.

These tests exercise the full path:
  BotWorkFlow (DB) -> ChatFlowEngine -> node executors -> DB result records

Real database, fake node executors (no LLM calls).
"""
import pytest
from django.utils import timezone

from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models import LLMSkill, WorkflowAttachmentAsset
from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory, WorkFlowTaskNodeResult, WorkFlowTaskResult
from apps.opspilot.services import builtin_tools
from apps.opspilot.services.workflow_attachment_service import create_workflow_attachment_asset
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.chat_flow_utils.nodes.action.action import NotifyNode
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

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


@pytest.mark.django_db(transaction=True)
def test_agent_node_sets_attachment_link_variable(mocker):
    variable_manager = VariableManager()
    variable_manager.set_variable("flow_id", "flow-1")
    variable_manager.set_variable(
        "flow_input",
        {
            "execution_id": "exec-attachment",
            "user_id": "tester",
            "node_id": "agent_node",
            "locale": "zh-Hans",
        },
    )
    skill = LLMSkill.objects.create(
        name="attachment-skill",
        team=[1],
        created_by="tester",
        domain="test.com",
        skill_prompt="system",
        tools=[
            {
                "id": builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_ID,
                "name": builtin_tools.BUILTIN_ATTACHMENT_FILE_TOOL_NAME,
                "kwargs": [],
            }
        ],
    )

    def invoke_chat_side_effect(params):
        create_workflow_attachment_asset(
            execution_id=params["execution_id"],
            attachment_id="agent_node",
            filename="report.md",
            content_bytes=b"# workflow report",
            mime_type="text/markdown",
            source_node_id="agent_node",
            flow_id="flow-1",
            created_by="tester",
        )
        return (
            {
                "message": "attachment generated",
                "success": True,
                "browser_steps": [],
            },
            {},
            {},
        )

    mocker.patch("apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.ChatService.invoke_chat", side_effect=invoke_chat_side_effect)

    node = AgentNode(variable_manager)
    result = node.execute(
        "agent_node",
        {
            "data": {
                "config": {
                    "inputParams": "last_message",
                    "outputParams": "last_message",
                    "agent": skill.id,
                }
            }
        },
        {"last_message": "generate report"},
    )

    asset = WorkflowAttachmentAsset.objects.get(execution_id="exec-attachment", attachment_id="agent_node")
    assert result["agent_node"] == asset.download_url
    assert variable_manager.get_variable("agent_node") == asset.download_url
    assert result["generated_attachment"]["filename"] == "report.md"


@pytest.mark.django_db(transaction=True)
def test_notification_node_sends_all_execution_attachments(mocker):
    variable_manager = VariableManager()
    variable_manager.set_variable("execution_id", "exec-notify")
    create_workflow_attachment_asset(
        execution_id="exec-notify",
        attachment_id="daily_report",
        filename="report.md",
        content_bytes=b"# workflow report",
        mime_type="text/markdown",
        source_node_id="agent_node",
        flow_id="flow-1",
        created_by="tester",
    )
    create_workflow_attachment_asset(
        execution_id="exec-notify",
        attachment_id="agent_node__1",
        filename="report-2.md",
        content_bytes=b"# workflow report 2",
        mime_type="text/markdown",
        source_node_id="agent_node",
        flow_id="flow-1",
        created_by="tester",
    )
    send_mock = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.action.action.SystemMgmt.send_msg_with_channel",
        return_value={"result": True, "message": "ok"},
    )

    node = NotifyNode(variable_manager)
    result = node.execute(
        "notify_node",
        {
            "data": {
                "config": {
                    "notificationType": "email",
                    "notificationMethod": 1,
                    "notificationTitle": "Daily Report",
                    "notificationContent": "See attachment",
                    "notificationRecipients": [1],
                    "outputParams": "last_message",
                }
            }
        },
        {"last_message": "ignored"},
    )

    attachments = send_mock.call_args.kwargs["attachments"]
    current_date = timezone.localtime().strftime("%Y%m%d")
    assert len(attachments) == 2
    assert attachments[0]["filename"] == f"{current_date}.md"
    assert attachments[1]["filename"] == f"{current_date}_2.md"
    assert result["last_message"] == "通知已发送: Daily Report"
