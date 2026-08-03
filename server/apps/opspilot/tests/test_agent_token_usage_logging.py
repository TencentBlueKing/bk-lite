from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.utils.agui_chat import _log_and_update_tokens_agui
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

pytestmark = pytest.mark.unit


def test_workflow_agent_persists_per_call_token_usage():
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

    with patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.agent.agent.SkillRequestLog.objects.create"
    ) as create_log:
        node._record_agent_token_usage(
            node_id="agent-1",
            skill_id=42,
            skill_name="k8s根因分析",
            chat_result={
                "message": "根因分析完成",
                "success": True,
                "prompt_tokens": 3000,
                "completion_tokens": 300,
                "total_tokens": 3300,
                "llm_call_count": 2,
                "token_usage_calls": usage_calls,
            },
            user_message="K8s Warning Failed on Pod/ns/pod-1",
            nats_only=True,
            log_source="NATS Agent",
        )

    response_detail = create_log.call_args.kwargs["response_detail"]
    assert response_detail["llm_call_count"] == 2
    assert response_detail["usage_calls"] == usage_calls


def test_execute_agui_persists_per_call_token_usage():
    usage_calls = [
        {
            "call_index": 1,
            "prompt_tokens": 500,
            "completion_tokens": 50,
            "total_tokens": 550,
            "reported": True,
            "visible_tool_count": 1,
            "visible_tools": ["diagnose_kubernetes_pod_issues"],
        }
    ]

    with patch(
        "apps.opspilot.utils.agui_chat.SkillRequestLog.objects.create"
    ) as create_log:
        _log_and_update_tokens_agui(
            final_stats={
                "content": [{"type": "TEXT_MESSAGE_CONTENT", "delta": "完成"}],
                "usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 50,
                    "total_tokens": 550,
                },
                "llm_call_count": 1,
                "usage_calls": usage_calls,
            },
            skill_name="根因分析 Agent",
            skill_id=41,
            current_ip="127.0.0.1",
            kwargs={},
            user_message="检查告警",
            show_think=False,
        )

    response_detail = create_log.call_args.kwargs["response_detail"]
    assert response_detail["llm_call_count"] == 1
    assert response_detail["usage_calls"] == usage_calls
