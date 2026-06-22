"""意图节点多轮：第二轮应能拿到第一轮的会话历史（端到端）。"""
import pytest

from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

ENTRY_NODE_ID = "openai-1777450801989"  # 来自 intent_workflow(id=4) 的 openai 入口


class RecordingAgentExecutor(BaseNodeExecutor):
    def execute(self, node_id, node_config, input_data):
        ik = node_config.get("data", {}).get("config", {}).get("inputParams", "last_message")
        ok = node_config.get("data", {}).get("config", {}).get("outputParams", "last_message")
        return {ok: f"handled:{input_data.get(ik, '')}"}


@pytest.mark.django_db(transaction=True)
def test_intent_node_injects_prior_turn_history(intent_workflow, mocker):
    invoke = mocker.patch(
        "apps.opspilot.utils.chat_flow_utils.nodes.intent.intent_classifier.ChatService.invoke_chat",
        return_value=({"message": "generate_script"}, {}, {}),
    )

    # 第一轮：落一条 user + 一条 bot 历史（session=s1）
    e1 = create_chat_flow_engine(intent_workflow, ENTRY_NODE_ID)
    e1.custom_node_executors["agents"] = RecordingAgentExecutor(e1.variable_manager)
    e1.execute({"last_message": "广州天气如何", "user_id": "u@test.com", "node_id": ENTRY_NODE_ID, "session_id": "s1"})

    # 第二轮：同一 session，意图节点应注入第一轮历史
    e2 = create_chat_flow_engine(intent_workflow, ENTRY_NODE_ID)
    e2.custom_node_executors["agents"] = RecordingAgentExecutor(e2.variable_manager)
    e2.execute({"last_message": "深圳呢", "user_id": "u@test.com", "node_id": ENTRY_NODE_ID, "session_id": "s1"})

    # 最后一次 invoke_chat 即第二轮意图分类
    chat_history = invoke.call_args_list[-1][0][0]["chat_history"]
    messages = [h["message"] for h in chat_history]
    assert "广州天气如何" in messages, f"第二轮意图节点缺少上一轮历史: {messages}"
    assert chat_history[-1]["message"] == "深圳呢"
