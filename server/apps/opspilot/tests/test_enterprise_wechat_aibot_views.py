from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCryptoError


@pytest.fixture
def request_factory():
    return RequestFactory()


def test_clean_text_message_removes_leading_robot_mention():
    result = EnterpriseWechatAibotChatFlowUtils.clean_text_message("@运维机器人   查询 CPU")

    assert result == "查询 CPU"


def test_clean_text_message_keeps_regular_text():
    result = EnterpriseWechatAibotChatFlowUtils.clean_text_message("查询 CPU")

    assert result == "查询 CPU"


def test_build_flow_input_uses_chatid_as_session_id():
    message = {
        "msgid": "m1",
        "aibotid": "bot-a",
        "chatid": "chat-1",
        "from": {"userid": "user-1"},
        "response_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
        "msgtype": "text",
        "text": {"content": "查询 CPU"},
    }

    result = EnterpriseWechatAibotChatFlowUtils.build_flow_input(
        bot_id=10,
        node_id="node-1",
        message=message,
        clean_text="查询 CPU",
    )

    assert result == {
        "last_message": "查询 CPU",
        "user_id": "user-1",
        "bot_id": 10,
        "node_id": "node-1",
        "channel": "enterprise_wechat_aibot",
        "is_third_party": True,
        "entry_type": "enterprise_wechat_aibot",
        "session_id": "chat-1",
        "response_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc",
    }


def test_agent_resolves_enterprise_wechat_aibot_as_third_party_trigger():
    result = AgentNode._resolve_trigger_type({"entry_type": "enterprise_wechat_aibot"})

    assert result == "third_party"


def test_enterprise_wechat_aibot_get_delegates_to_handler(request_factory):
    from apps.opspilot.views import execute_chat_flow_enterprise_wechat_aibot

    request = request_factory.get(
        "/api/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/1/",
        {"msg_signature": "s", "timestamp": "1", "nonce": "n", "echostr": "e"},
    )

    with patch("apps.opspilot.views.EnterpriseWechatAibotChatFlowUtils") as utils_cls:
        utils_cls.return_value.handle_request.return_value = HttpResponse("ok")
        response = execute_chat_flow_enterprise_wechat_aibot(request, 1)

    assert response.status_code == 200
    assert response.content == b"ok"
    utils_cls.assert_called_once_with(1)
    utils_cls.return_value.handle_request.assert_called_once_with(request)


def test_handle_request_uses_workflow_node_config_for_url_verification(request_factory):
    request = request_factory.get("/callback")
    workflow = SimpleNamespace(
        flow_json={
            "nodes": [
                {
                    "id": "node-1",
                    "type": "enterprise_wechat_aibot",
                    "data": {"config": {"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}},
                }
            ]
        }
    )

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.Bot.objects") as bot_objects, patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.BotWorkFlow.objects"
    ) as workflow_objects, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "handle_url_verification",
        return_value=HttpResponse("plain"),
    ) as handle_verify:
        bot_objects.filter.return_value.first.return_value = SimpleNamespace(id=10)
        workflow_objects.filter.return_value.first.return_value = workflow
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_request(request)

    assert response.content == b"plain"
    handle_verify.assert_called_once_with(request, {"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}})


def test_handle_request_returns_success_when_bot_missing(request_factory):
    request = request_factory.get("/callback")

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.Bot.objects") as bot_objects:
        bot_objects.filter.return_value.first.return_value = None
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_request(request)

    assert response.status_code == 200
    assert response.content == b"success"


def test_handle_request_returns_success_when_workflow_missing(request_factory):
    request = request_factory.get("/callback")

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.Bot.objects") as bot_objects, patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.BotWorkFlow.objects"
    ) as workflow_objects:
        bot_objects.filter.return_value.first.return_value = SimpleNamespace(id=10)
        workflow_objects.filter.return_value.first.return_value = None
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_request(request)

    assert response.status_code == 200
    assert response.content == b"success"


def test_handle_request_returns_success_when_aibot_node_missing(request_factory):
    request = request_factory.get("/callback")
    workflow = SimpleNamespace(flow_json={"nodes": [{"id": "other", "type": "restful"}]})

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.Bot.objects") as bot_objects, patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.BotWorkFlow.objects"
    ) as workflow_objects:
        bot_objects.filter.return_value.first.return_value = SimpleNamespace(id=10)
        workflow_objects.filter.return_value.first.return_value = workflow
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_request(request)

    assert response.status_code == 200
    assert response.content == b"success"


def test_handle_request_rejects_unsupported_method(request_factory):
    request = request_factory.delete("/callback")
    workflow = SimpleNamespace(
        flow_json={
            "nodes": [
                {
                    "id": "node-1",
                    "type": "enterprise_wechat_aibot",
                    "data": {"config": {"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}},
                }
            ]
        }
    )

    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.Bot.objects") as bot_objects, patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.BotWorkFlow.objects"
    ) as workflow_objects:
        bot_objects.filter.return_value.first.return_value = SimpleNamespace(id=10)
        workflow_objects.filter.return_value.first.return_value = workflow
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_request(request)

    assert response.status_code == 405


def test_handle_url_verification_returns_plaintext(request_factory):
    request = request_factory.get(
        "/callback",
        {"msg_signature": "s", "timestamp": "1", "nonce": "n", "echostr": "e"},
    )
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
        return_value="plain",
    ):
        response = EnterpriseWechatAibotChatFlowUtils.handle_url_verification(request, config)

    assert response.status_code == 200
    assert response.content == b"plain"


def test_handle_url_verification_returns_fail_for_invalid_config(request_factory):
    request = request_factory.get("/callback")

    response = EnterpriseWechatAibotChatFlowUtils.handle_url_verification(request, {"connectionMode": "webhook", "webhook": {}})

    assert response.status_code == 400
    assert response.content == b"fail"


def test_handle_url_verification_returns_fail_for_crypto_error(request_factory):
    request = request_factory.get("/callback")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
        side_effect=EnterpriseWechatAibotCryptoError("boom"),
    ):
        response = EnterpriseWechatAibotChatFlowUtils.handle_url_verification(request, config)

    assert response.status_code == 400
    assert response.content == b"fail"


def test_handle_aibot_message_dispatches_text_message(request_factory):
    request = request_factory.post(
        "/callback",
        data=b'{"encrypt":"abc"}',
        content_type="application/json",
        QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
    )
    config = {
        "connectionMode": "webhook",
        "webhook": {"token": "token", "encodingAESKey": "key", "aibotid": "bot-a"},
    }
    message = {
        "msgid": "m1",
        "aibotid": "bot-a",
        "chatid": "chat-1",
        "from": {"userid": "user-1"},
        "response_url": "https://example.com/response",
        "msgtype": "text",
        "text": {"content": "@机器人 查询 CPU"},
    }

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "is_message_processed",
        return_value=False,
    ), patch(
        "apps.opspilot.tasks.process_enterprise_wechat_aibot_message.delay"
    ) as delay:
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_called_once_with(
        bot_id=10,
        msg_id="m1",
        message={
            "last_message": "查询 CPU",
            "user_id": "user-1",
            "bot_id": 10,
            "node_id": "node-1",
            "channel": "enterprise_wechat_aibot",
            "is_third_party": True,
            "entry_type": "enterprise_wechat_aibot",
            "session_id": "chat-1",
            "response_url": "https://example.com/response",
        },
        sender_id="user-1",
        config={
            "connectionMode": "webhook",
            "webhook": {"token": "token", "encodingAESKey": "key", "aibotid": "bot-a"},
            "node_id": "node-1",
            "response_url": "https://example.com/response",
        },
    )


def test_handle_aibot_message_skips_aibotid_mismatch(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {
        "connectionMode": "webhook",
        "webhook": {"token": "token", "encodingAESKey": "key", "aibotid": "expected"},
    }
    message = {"msgid": "m1", "aibotid": "actual", "msgtype": "text", "text": {"content": "hi"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch("apps.opspilot.tasks.process_enterprise_wechat_aibot_message.delay") as delay:
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_not_called()


def test_handle_aibot_message_does_not_dispatch_duplicate(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}
    message = {"msgid": "m1", "msgtype": "text", "text": {"content": "hi"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "is_message_processed",
        return_value=True,
    ), patch(
        "apps.opspilot.tasks.process_enterprise_wechat_aibot_message.delay"
    ) as delay:
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_not_called()


def test_handle_aibot_message_returns_success_on_decrypt_error(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        side_effect=EnterpriseWechatAibotCryptoError("boom"),
    ):
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"


def test_handle_aibot_message_returns_success_when_msgid_missing(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value={"msgtype": "text", "text": {"content": "hi"}},
    ):
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"


def test_handle_aibot_message_dispatches_unsupported_reply_without_marking_completed_before_send(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "webhook", "webhook": {"token": "token", "encodingAESKey": "key"}}
    message = {"msgid": "m1", "msgtype": "image", "response_url": "https://example.com/response"}

    with patch(
        "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
        return_value=message,
    ), patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "is_message_processed",
        return_value=False,
    ), patch(
        "apps.opspilot.tasks.process_enterprise_wechat_aibot_reply.delay"
    ) as reply_delay, patch.object(
        EnterpriseWechatAibotChatFlowUtils,
        "mark_message_completed",
    ) as mark_completed:
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    reply_delay.assert_called_once_with(10, "m1", "https://example.com/response", "当前仅支持文本消息")
    mark_completed.assert_not_called()


def test_websocket_mode_is_not_executed(request_factory):
    request = request_factory.post("/callback", data=b'{"encrypt":"abc"}', content_type="application/json")
    config = {"connectionMode": "websocket", "websocket": {"botId": "bot-id", "secret": "secret"}}

    with patch("apps.opspilot.tasks.process_enterprise_wechat_aibot_message.delay") as delay:
        response = EnterpriseWechatAibotChatFlowUtils(10).handle_aibot_message(request, "node-1", config)

    assert response.status_code == 200
    assert response.content == b"success"
    delay.assert_not_called()


def test_send_markdown_reply_ignores_empty_response_url():
    with patch("apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.requests.post") as post:
        EnterpriseWechatAibotChatFlowUtils.send_markdown_reply("", "hello")

    post.assert_not_called()


def test_truncate_markdown_limits_utf8_bytes():
    result = EnterpriseWechatAibotChatFlowUtils.truncate_markdown("你" * 8000)

    assert len(result.encode("utf-8")) <= 20480
    assert result.endswith("内容过长，已截断")
