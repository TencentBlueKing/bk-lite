"""conversation_history helper 单元测试。"""
import pytest
from django.utils import timezone

from apps.opspilot.models.bot_mgmt import WorkFlowConversationHistory
from apps.opspilot.utils.chat_flow_utils.conversation_history import load_session_history


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
