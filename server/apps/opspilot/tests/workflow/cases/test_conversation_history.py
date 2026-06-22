"""conversation_history helper 单元测试。"""
import pytest
from django.utils import timezone

from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory
from apps.opspilot.utils.chat_flow_utils.conversation_history import load_session_history
from apps.opspilot.utils.chat_flow_utils.conversation_history import build_node_chat_history
from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager


def _add_history(bot_id, role, content, execution_id, session_id="s1", user_id="u@test.com"):
    return WorkFlowConversationHistory.objects.create(
        bot_id=bot_id,
        node_id="entry",
        user_id=user_id,
        conversation_role=role,
        conversation_content=content,
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id=session_id,
        execution_id=execution_id,
    )


@pytest.mark.django_db(transaction=True)
class TestLoadSessionHistory:
    def test_returns_prior_turns_in_chronological_order(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "bot", "广州20-28度", "exec-1")

        history = load_session_history(bot.id, "u@test.com", "s1", exclude_execution_id="exec-2")

        assert history == [
            {"event": "user", "message": "广州天气如何"},
            {"event": "bot", "message": "广州20-28度"},
        ]

    def test_excludes_current_execution(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "user", "深圳呢", "exec-2")  # 当前轮已落库，必须被排除

        history = load_session_history(bot.id, "u@test.com", "s1", exclude_execution_id="exec-2")

        assert [h["message"] for h in history] == ["广州天气如何"]

    def test_empty_session_id_returns_empty(self, bot):
        _add_history(bot.id, "user", "x", "exec-1", session_id="")
        assert load_session_history(bot.id, "u@test.com", "", exclude_execution_id="exec-2") == []

    def test_missing_bot_id_returns_empty(self):
        assert load_session_history(None, "u@test.com", "s1", exclude_execution_id="exec-2") == []


def _vm_with_anchor(bot_id, anchor="深圳呢", session_id="s1", execution_id="exec-2", user_id="u@test.com"):
    vm = VariableManager()
    vm.set_variable("original_user_message", anchor)
    vm.set_variable("bot_id", bot_id)
    vm.set_variable("execution_id", execution_id)
    vm.set_variable("flow_input", {"user_id": user_id, "session_id": session_id})
    return vm


@pytest.mark.django_db(transaction=True)
class TestBuildNodeChatHistory:
    def test_injects_history_when_input_is_user_turn(self, bot):
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        _add_history(bot.id, "bot", "广州20-28度", "exec-1")
        vm = _vm_with_anchor(bot.id)

        result = build_node_chat_history(vm, raw_input_message="深圳呢", final_message="深圳呢")

        assert result[0] == {"event": "user", "message": "广州天气如何"}
        assert result[1] == {"event": "bot", "message": "广州20-28度"}
        assert result[-1] == {"event": "user", "message": "深圳呢"}

    def test_no_history_when_input_is_upstream_output(self, bot):
        # 下游加工节点：输入是上游 agent 的输出，不等于用户原话 → 不注入
        _add_history(bot.id, "user", "广州天气如何", "exec-1")
        vm = _vm_with_anchor(bot.id)

        result = build_node_chat_history(
            vm, raw_input_message="agent_processed: 广州天气如何", final_message="agent_processed: 广州天气如何"
        )

        assert result == [{"event": "user", "message": "agent_processed: 广州天气如何"}]

    def test_no_history_when_anchor_missing(self, bot):
        vm = VariableManager()  # 没有 original_user_message
        result = build_node_chat_history(vm, raw_input_message="深圳呢", final_message="深圳呢")
        assert result == [{"event": "user", "message": "深圳呢"}]
