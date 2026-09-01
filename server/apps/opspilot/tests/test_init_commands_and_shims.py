"""OpsPilot 兼容 shim、初始化命令与用户创建信号。"""
from io import StringIO
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command

from apps.base.models import User
from apps.opspilot.signals.user_create_signal import user_create_signal
from apps.opspilot.utils import approval, dingtalk_chat_flow_utils, mcp_client, wechat_official_chat_flow_utils

pytestmark = pytest.mark.django_db


def test_compat_shims_reexport_services():
    assert callable(approval.submit_approval_decision)
    assert callable(approval.wait_for_approval)
    assert mcp_client.MCPClient is not None
    assert dingtalk_chat_flow_utils.DingTalkChatFlowUtils is not None
    assert callable(dingtalk_chat_flow_utils.is_valid_dingtalk_url)
    assert wechat_official_chat_flow_utils.WechatOfficialChatFlowUtils is not None


def test_init_bot_llm_chatflow_commands(monkeypatch):
    bot = MagicMock()
    llm = MagicMock()
    flow = MagicMock()
    monkeypatch.setattr("apps.opspilot.management.commands.init_bot.BotInitService", lambda owner: bot)
    monkeypatch.setattr("apps.opspilot.management.commands.init_llm.ModelProviderInitService", lambda owner="admin": llm)
    monkeypatch.setattr("apps.opspilot.management.commands.init_chatflow.ChatFlowInitService", lambda: flow)
    call_command("init_bot")
    bot.init.assert_called_once_with()
    call_command("init_llm")
    llm.init.assert_called_once_with()
    stdout = StringIO()
    call_command("init_chatflow", stdout=stdout)
    flow.init.assert_called_once_with()
    assert "ChatFlow 初始化完成" in stdout.getvalue()


def test_user_create_signal_inits_bot_and_channel(monkeypatch):
    bot = MagicMock()
    channel = MagicMock()
    monkeypatch.setattr("apps.opspilot.signals.user_create_signal.BotInitService", lambda owner: bot)
    monkeypatch.setattr("apps.opspilot.signals.user_create_signal.ChannelInitService", lambda owner: channel)
    user_create_signal()
    admin = User.objects.get(username="admin")
    assert admin.is_superuser is True
    bot.init.assert_called_once_with()
    channel.init.assert_called_once_with()
