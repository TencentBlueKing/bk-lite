"""引擎初始化应写入跨轮历史所需的锚点变量。"""

import pytest

from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


@pytest.mark.django_db(transaction=True)
def test_initialize_variables_sets_history_anchors(bot_workflow):
    engine = create_chat_flow_engine(bot_workflow, "entry_node")

    engine._initialize_variables({"last_message": "广州天气如何", "user_id": "u@test.com", "session_id": "s1"})

    assert engine.variable_manager.get_variable("original_user_message") == "广州天气如何"
    assert engine.variable_manager.get_variable("bot_id") == bot_workflow.bot_id
