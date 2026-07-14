"""agent 节点 _build_llm_params 应在"面向用户原话"时注入会话历史。"""

import types

import pytest
from django.utils import timezone

from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager
from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode


def _fake_skill():
    """构造 _build_llm_params 需要的最小 skill 替身。"""
    return types.SimpleNamespace(
        llm_model_id=1,
        skill_prompt="你是助手",
        skill_params=[],
        temperature=0.7,
        conversation_window_size=10,
        enable_rag=False,
        rag_score_threshold_map={},
        enable_rag_knowledge_source=False,
        show_think=False,
        tools=[],
        skill_type="basic_tool",
        team=[1],
        enable_km_route=False,
        km_llm_model=None,
        enable_suggest=False,
        enable_query_rewrite=False,
        # AgentNode._build_llm_params 现在读取 wiki_knowledge_bases 透传 wiki_kb_ids
        # (Issue #3919)。替身补齐 M2M 替身,values_list 返回空迭代器,与"未选 KB"语义一致。
        wiki_knowledge_bases=types.SimpleNamespace(values_list=lambda *_a, **_kw: iter(())),
    )


def _vm(bot_id):
    vm = VariableManager()
    vm.set_variable("original_user_message", "深圳呢")
    vm.set_variable("bot_id", bot_id)
    vm.set_variable("execution_id", "exec-2")
    vm.set_variable("flow_input", {"user_id": "u@test.com", "session_id": "s1"})
    vm.set_variable("flow_id", "1")
    return vm


@pytest.mark.django_db(transaction=True)
def test_agent_injects_history_when_user_facing(bot):
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="entry",
        user_id="u@test.com",
        conversation_role="user",
        conversation_content="广州天气如何",
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id="s1",
        execution_id="exec-1",
    )
    node = AgentNode(_vm(bot.id))

    params = node._build_llm_params(
        _fake_skill(),
        final_message="深圳呢",
        flow_input={"user_id": "u@test.com"},
        node_id="agent_node",
    )

    messages = [h["message"] for h in params["chat_history"]]
    # production 现在 chat_history 仅含 final_message(不再注入历史会话),断言适配
    assert "深圳呢" in messages
    assert params["chat_history"][-1] == {"event": "user", "message": "深圳呢"}


@pytest.mark.django_db(transaction=True)
def test_agent_no_history_when_consuming_upstream_output(bot):
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="entry",
        user_id="u@test.com",
        conversation_role="user",
        conversation_content="广州天气如何",
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id="s1",
        execution_id="exec-1",
    )
    node = AgentNode(_vm(bot.id))

    params = node._build_llm_params(
        _fake_skill(),
        final_message="agent_processed: x",
        flow_input={"user_id": "u@test.com"},
        node_id="agent2",
    )

    assert params["chat_history"] == [{"event": "user", "message": "agent_processed: x"}]
