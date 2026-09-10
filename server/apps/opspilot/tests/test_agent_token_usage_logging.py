import logging
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.utils.agui_chat import _log_and_update_tokens_agui
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

pytestmark = pytest.mark.unit

_AGUI_CALL_TEMPLATE = (
    "AGUI token usage call recorded: skill_id=%s, skill_name=%s, "
    "call_index=%s, visible_tool_count=%s, visible_tools=%s, "
    "prompt_tokens=%s, completion_tokens=%s, total_tokens=%s"
)
_AGUI_SUMMARY_TEMPLATE = (
    "AGUI token usage recorded: skill_id=%s, skill_name=%s, llm_call_count=%s, " "prompt_tokens=%s, completion_tokens=%s, total_tokens=%s"
)
_WORKFLOW_CALL_TEMPLATE = (
    "%s token usage call recorded: entry_type=%s, bot_id=%s, execution_id=%s, "
    "node_id=%s, skill_id=%s, call_index=%s, visible_tool_count=%s, "
    "visible_tools=%s, prompt_tokens=%s, completion_tokens=%s, total_tokens=%s"
)
_WORKFLOW_SUMMARY_TEMPLATE = (
    "%s token usage recorded: entry_type=%s, bot_id=%s, execution_id=%s, node_id=%s, "
    "skill_id=%s, skill_name=%s, llm_call_count=%s, prompt_tokens=%s, "
    "completion_tokens=%s, total_tokens=%s"
)
_USER_MESSAGE_SENTINEL = "K8s Warning Failed on Pod/ns/pod-1 TOKEN_PAYLOAD_SENTINEL"
_RESPONSE_SENTINEL = "根因分析完成 RESPONSE_PAYLOAD_SENTINEL"


def test_workflow_agent_persists_per_call_token_usage(caplog):
    node = AgentNode.__new__(AgentNode)
    node.variable_manager = MagicMock()
    node.variable_manager.get_variable.side_effect = lambda name, default=None: {
        "flow_input": {
            "entry_type": "nats",
            "bot_id": 6,
            "execution_id": "exec-1",
        },
        "execution_id": "exec-1",
    }.get(name, default)
    usage_calls = [
        {
            "call_index": 1,
            "prompt_tokens": 1200,
            "completion_tokens": 80,
            "total_tokens": 1280,
            "reported": True,
            "visible_tool_count": 2,
            "visible_tools": [
                "diagnose_kubernetes_pod_issues",
                "list_kubernetes_events",
            ],
        },
        {
            "call_index": 2,
            "prompt_tokens": 1800,
            "completion_tokens": 220,
            "total_tokens": 2020,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["get_kubernetes_pod_logs"],
        },
    ]
    caplog.set_level(logging.DEBUG, logger="opspilot")

    with patch("apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.SkillRequestLog.objects.create") as create_log:
        node._record_agent_token_usage(
            node_id="agent-1",
            skill_id=42,
            skill_name="k8s根因分析",
            chat_result={
                "message": _RESPONSE_SENTINEL,
                "success": True,
                "prompt_tokens": 3000,
                "completion_tokens": 300,
                "total_tokens": 3300,
                "llm_call_count": 2,
                "token_usage_calls": usage_calls,
            },
            user_message=_USER_MESSAGE_SENTINEL,
            nats_only=True,
            log_source="NATS Agent",
        )

    response_detail = create_log.call_args.kwargs["response_detail"]
    assert response_detail["llm_call_count"] == 2
    assert response_detail["usage_calls"] == usage_calls
    assert response_detail["response"] == _RESPONSE_SENTINEL
    assert create_log.call_args.kwargs["user_message"] == _USER_MESSAGE_SENTINEL

    debug_records = [record for record in caplog.records if record.msg == _WORKFLOW_CALL_TEMPLATE]
    info_records = [record for record in caplog.records if record.msg == _WORKFLOW_SUMMARY_TEMPLATE]
    assert len(debug_records) == 2
    assert all(record.name == "opspilot" and record.levelno == logging.DEBUG for record in debug_records)
    assert debug_records[0].args == (
        "NATS Agent",
        "nats",
        6,
        "exec-1",
        "agent-1",
        42,
        1,
        2,
        ["diagnose_kubernetes_pod_issues", "list_kubernetes_events"],
        1200,
        80,
        1280,
    )
    assert debug_records[1].args == (
        "NATS Agent",
        "nats",
        6,
        "exec-1",
        "agent-1",
        42,
        2,
        1,
        ["get_kubernetes_pod_logs"],
        1800,
        220,
        2020,
    )
    assert len(info_records) == 1
    info_record = info_records[0]
    assert info_record.name == "opspilot"
    assert info_record.levelno == logging.INFO
    assert info_record.args == (
        "NATS Agent",
        "nats",
        6,
        "exec-1",
        "agent-1",
        42,
        "k8s根因分析",
        2,
        3000,
        300,
        3300,
    )
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    debug_rendered = debug_records[0].getMessage()
    info_rendered = info_record.getMessage()
    debug_formatted = formatter.format(debug_records[0])
    info_formatted = formatter.format(info_record)
    assert debug_rendered.startswith("NATS Agent token usage call recorded:")
    assert "call_index=1" in debug_rendered
    assert info_rendered.startswith("NATS Agent token usage recorded:")
    assert "llm_call_count=2" in info_rendered
    assert "total_tokens=3300" in info_rendered
    for text in (debug_rendered, info_rendered, debug_formatted, info_formatted, caplog.text):
        assert _USER_MESSAGE_SENTINEL not in text
        assert _RESPONSE_SENTINEL not in text
    assert not any(record.levelno >= logging.INFO and record.msg == _WORKFLOW_CALL_TEMPLATE for record in caplog.records)


def test_execute_agui_persists_per_call_token_usage(caplog):
    usage_calls = [
        {
            "call_index": 1,
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["diagnose_kubernetes_pod_issues"],
        },
        {
            "call_index": 2,
            "prompt_tokens": 800,
            "completion_tokens": 70,
            "total_tokens": 870,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["get_kubernetes_previous_pod_logs"],
        },
    ]
    user_message = "检查告警 TOKEN_PAYLOAD_SENTINEL"
    response_content = [{"type": "TEXT_MESSAGE_CONTENT", "delta": "完成 RESPONSE_PAYLOAD_SENTINEL"}]
    caplog.set_level(logging.DEBUG, logger="opspilot")

    with patch("apps.opspilot.utils.agui_chat.SkillRequestLog.objects.create") as create_log:
        _log_and_update_tokens_agui(
            final_stats={
                "content": response_content,
                "usage": {
                    "prompt_tokens": 1300,
                    "completion_tokens": 120,
                    "total_tokens": 1420,
                },
                "llm_call_count": 2,
                "usage_calls": usage_calls,
            },
            skill_name="根因分析 Agent",
            skill_id=41,
            current_ip="127.0.0.1",
            kwargs={},
            user_message=user_message,
            show_think=False,
        )

    response_detail = create_log.call_args.kwargs["response_detail"]
    assert response_detail["llm_call_count"] == 2
    assert response_detail["usage_calls"] == usage_calls
    assert response_detail["response"] == response_content
    assert create_log.call_args.kwargs["user_message"] == user_message

    debug_records = [record for record in caplog.records if record.msg == _AGUI_CALL_TEMPLATE]
    info_records = [record for record in caplog.records if record.msg == _AGUI_SUMMARY_TEMPLATE]
    assert len(debug_records) == 2
    assert all(record.name == "opspilot" and record.levelno == logging.DEBUG for record in debug_records)
    assert debug_records[0].args == (
        41,
        "根因分析 Agent",
        1,
        1,
        ["diagnose_kubernetes_pod_issues"],
        500,
        50,
        550,
    )
    assert debug_records[1].args == (
        41,
        "根因分析 Agent",
        2,
        1,
        ["get_kubernetes_previous_pod_logs"],
        800,
        70,
        870,
    )
    assert len(info_records) == 1
    info_record = info_records[0]
    assert info_record.name == "opspilot"
    assert info_record.levelno == logging.INFO
    assert info_record.args == (41, "根因分析 Agent", 2, 1300, 120, 1420)
    formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    debug_rendered = debug_records[0].getMessage()
    info_rendered = info_record.getMessage()
    debug_formatted = formatter.format(debug_records[0])
    info_formatted = formatter.format(info_record)
    assert debug_rendered == (
        "AGUI token usage call recorded: skill_id=41, skill_name=根因分析 Agent, "
        "call_index=1, visible_tool_count=1, visible_tools=['diagnose_kubernetes_pod_issues'], "
        "prompt_tokens=500, completion_tokens=50, total_tokens=550"
    )
    assert info_rendered == (
        "AGUI token usage recorded: skill_id=41, skill_name=根因分析 Agent, llm_call_count=2, "
        "prompt_tokens=1300, completion_tokens=120, total_tokens=1420"
    )
    for text in (debug_rendered, info_rendered, debug_formatted, info_formatted, caplog.text):
        assert "TOKEN_PAYLOAD_SENTINEL" not in text
        assert "RESPONSE_PAYLOAD_SENTINEL" not in text
    assert not any(record.levelno >= logging.INFO and record.msg == _AGUI_CALL_TEMPLATE for record in caplog.records)
