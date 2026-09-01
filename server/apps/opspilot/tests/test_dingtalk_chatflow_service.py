"""钉钉 ChatFlow：Bot/节点校验、签名、发信 SSRF、引擎执行与 token。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.http import JsonResponse

from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

pytestmark = pytest.mark.django_db


def _utils(bot_id=1):
    u = DingTalkChatFlowUtils.__new__(DingTalkChatFlowUtils)
    u.bot_id = bot_id
    return u


def test_validate_bot_and_workflow_offline_missing_empty():
    utils = _utils(1)
    flow, err = utils.validate_bot_and_workflow()
    assert flow is None
    assert isinstance(err, JsonResponse)

    bot = Bot.objects.create(name="dt-bot", team=[1], online=False)
    utils.bot_id = bot.id
    flow, err = utils.validate_bot_and_workflow()
    assert err is not None

    bot.online = True
    bot.save()
    flow, err = utils.validate_bot_and_workflow()
    assert err is not None
    assert b"Workflow not configured" in err.content

    wf = BotWorkFlow.objects.create(bot=bot, flow_json={})
    flow, err = utils.validate_bot_and_workflow()
    assert err is not None
    assert b"empty" in err.content.lower()

    wf.flow_json = {"nodes": []}
    wf.save()
    flow, err = utils.validate_bot_and_workflow()
    assert err is None
    assert flow.id == wf.id


def test_get_dingtalk_node_config_missing_and_required_params():
    utils = _utils()
    empty = SimpleNamespace(flow_json={"nodes": [{"type": "wechat", "id": "n1", "data": {}}]})
    cfg, err = utils.get_dingtalk_node_config(empty)
    assert cfg is None and err is not None

    missing = SimpleNamespace(flow_json={"nodes": [{"type": "dingtalk", "id": "n-dt", "data": {"config": {"client_id": "a"}}}]})
    cfg, err = utils.get_dingtalk_node_config(missing)
    assert cfg is None
    assert b"client_secret" in err.content

    ok = SimpleNamespace(
        flow_json={
            "nodes": [
                {
                    "type": "dingtalk",
                    "id": "n-dt",
                    "data": {"config": {"client_id": "a", "client_secret": "b"}},
                }
            ]
        }
    )
    cfg, err = utils.get_dingtalk_node_config(ok)
    assert err is None
    assert cfg["node_id"] == "n-dt"
    assert cfg["client_id"] == "a"


def test_send_message_rejects_empty_and_ssrf_and_posts():
    utils = _utils()
    assert utils.send_message("", "text", {"content": "hi"}) is False
    assert utils.send_message("https://evil.example/hook", "text", {"content": "hi"}) is False
    with patch("apps.opspilot.services.dingtalk_chat_flow_utils.requests.post") as post:
        post.return_value.json.return_value = {"errcode": 1, "errmsg": "fail"}
        assert utils.send_message("https://oapi.dingtalk.com/robot/send", "text", {"content": "hi"}) is False
        post.return_value.json.return_value = {"errcode": 0}
        assert utils.send_message("https://oapi.dingtalk.com/robot/send", "text", {"content": "hi"}) is True
        post.side_effect = RuntimeError("timeout")
        assert utils.send_message("https://oapi.dingtalk.com/robot/send", "text", {"content": "hi"}) is False


def test_get_access_token_success_and_error():
    utils = _utils()
    with patch("apps.opspilot.services.dingtalk_chat_flow_utils.requests.get") as get:
        get.return_value.json.return_value = {"errcode": 0, "access_token": "tok"}
        assert utils.get_access_token("k", "s") == "tok"
        get.return_value.json.return_value = {"errcode": 88, "errmsg": "bad"}
        with pytest.raises(Exception, match="获取access_token失败"):
            utils.get_access_token("k", "s")


def test_execute_chatflow_uses_engine_and_prefers_content():
    utils = _utils(9)
    engine = MagicMock()
    engine.execute.return_value = {"content": "回复A"}
    flow = SimpleNamespace()
    with patch("apps.opspilot.services.dingtalk_chat_flow_utils.create_chat_flow_engine", return_value=engine):
        assert utils.execute_chatflow_with_message(flow, "n1", "你好", "u1") == "回复A"
        engine.execute.return_value = {"data": "回复B"}
        assert utils.execute_chatflow_with_message(flow, "n1", "你好", "u1") == "回复B"
        engine.execute.return_value = None
        assert utils.execute_chatflow_with_message(flow, "n1", "你好", "u1") == "处理完成"


def test_send_reply_skips_empty_and_delegates():
    utils = _utils()
    with patch.object(utils, "send_message", return_value=True) as send:
        utils.send_reply("", "sid", {"webhook_url": "https://oapi.dingtalk.com/x"})
        send.assert_not_called()
        utils.send_reply("hello", "sid", {"webhook_url": "https://oapi.dingtalk.com/x"})
        send.assert_called_once()
        assert send.call_args.args[1] == "text"
