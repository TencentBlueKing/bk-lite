"""钉钉和微信公众号渠道的公开消息契约。"""

import hashlib
import hmac
import json
from base64 import b64encode
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa: F401
import pytest

from apps.opspilot.services import dingtalk_chat_flow_utils as dingtalk
from apps.opspilot.services import wechat_official_chat_flow_utils as wechat


pytestmark = pytest.mark.unit


def response_json(response):
    return json.loads(response.content)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://oapi.dingtalk.com/robot/send", True),
        ("https://api.dingtalk.com/v1/messages", True),
        ("https://stream.dingtalk.com/callback", True),
        ("https://evil.example.com", False),
        ("https://oapi.dingtalk.com@evil.example.com", False),
        ("file://oapi.dingtalk.com/etc/passwd", False),
        ("https://oapi.dingtalk.com\\@evil.example.com", False),
        ("", False),
    ],
)
def test_dingtalk_url_allowlist_rejects_parser_bypasses(url, allowed):
    assert dingtalk.is_valid_dingtalk_url(url) is allowed


def test_dingtalk_node_config_requires_credentials_and_exposes_node_id():
    utils = dingtalk.DingTalkChatFlowUtils(bot_id=7)
    valid_flow = NS(
        flow_json={
            "nodes": [
                {
                    "id": "ding-1",
                    "type": "dingtalk",
                    "data": {
                        "config": {
                            "client_id": "client",
                            "client_secret": "secret",
                        }
                    },
                }
            ]
        }
    )
    missing_flow = NS(
        flow_json={
            "nodes": [
                {
                    "id": "ding-2",
                    "type": "dingtalk",
                    "data": {"config": {"client_id": "client"}},
                }
            ]
        }
    )

    config, error = utils.get_dingtalk_node_config(valid_flow)
    missing, missing_error = utils.get_dingtalk_node_config(missing_flow)

    assert error is None
    assert config["node_id"] == "ding-1"
    assert missing is None
    assert response_json(missing_error)["message"] == (
        "Missing config: client_secret"
    )


def test_dingtalk_signature_and_chatflow_result_contract():
    utils = dingtalk.DingTalkChatFlowUtils(bot_id=7)
    timestamp = "1710000000000"
    secret = "app-secret"
    signature = b64encode(
        hmac.new(
            secret.encode(),
            f"{timestamp}\n{secret}".encode(),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode()
    engine = NS(execute=MagicMock(return_value={"content": "service healthy"}))
    with patch.object(
        dingtalk,
        "create_chat_flow_engine",
        return_value=engine,
    ):
        result = utils.execute_chatflow_with_message(
            NS(),
            "ding-1",
            "check service",
            "user-1",
            is_third_party=True,
        )

    assert utils.verify_signature(timestamp, signature, secret) is True
    assert utils.verify_signature(timestamp, "invalid", secret) is False
    assert result == "service healthy"
    engine.execute.assert_called_once_with(
        {
            "last_message": "check service",
            "user_id": "user-1",
            "bot_id": 7,
            "node_id": "ding-1",
            "channel": "ding_talk",
            "is_third_party": True,
        }
    )


def test_dingtalk_access_token_and_message_delivery_use_official_endpoints():
    utils = dingtalk.DingTalkChatFlowUtils(bot_id=7)
    token_response = NS(
        json=lambda: {"errcode": 0, "access_token": "token-1"}
    )
    message_response = NS(json=lambda: {"errcode": 0})
    with (
        patch.object(dingtalk.requests, "get", return_value=token_response) as get,
        patch.object(
            dingtalk.requests,
            "post",
            return_value=message_response,
        ) as post,
    ):
        token = utils.get_access_token("client", "secret")
        sent = utils.send_message(
            "https://oapi.dingtalk.com/robot/send?access_token=x",
            "text",
            {"content": "healthy"},
        )

    assert token == "token-1"
    assert sent is True
    get.assert_called_once_with(
        "https://oapi.dingtalk.com/gettoken",
        params={"appkey": "client", "appsecret": "secret"},
        timeout=10,
    )
    assert post.call_args.kwargs["json"] == {
        "msgtype": "text",
        "text": {"content": "healthy"},
    }


def test_dingtalk_message_delivery_rejects_untrusted_webhook_and_api_error():
    utils = dingtalk.DingTalkChatFlowUtils(bot_id=7)
    with patch.object(dingtalk.requests, "post") as post:
        assert (
            utils.send_message(
                "https://evil.example.com/steal",
                "text",
                {"content": "secret"},
            )
            is False
        )
    with patch.object(
        dingtalk.requests,
        "post",
        return_value=NS(json=lambda: {"errcode": 400, "errmsg": "invalid"}),
    ):
        failed = utils.send_message(
            "https://api.dingtalk.com/v1/messages",
            "text",
            {"content": "hello"},
        )

    post.assert_not_called()
    assert failed is False


def test_dingtalk_http_message_dispatches_celery_once():
    utils = dingtalk.DingTalkChatFlowUtils(bot_id=7)
    request = NS(
        body=json.dumps(
            {
                "msgtype": "text",
                "text": {"content": "check database"},
                "senderStaffId": "user-1",
                "msgId": "msg-1",
                "sessionWebhook": "https://oapi.dingtalk.com/robot/send",
            }
        ).encode(),
        headers={},
    )
    task = MagicMock()
    with (
        patch.object(utils, "is_message_processed", return_value=False),
        patch(
            "apps.opspilot.tasks.process_dingtalk_message.delay",
            task,
        ),
    ):
        response = utils.handle_dingtalk_message(
            request,
            NS(),
            {"client_secret": "secret", "node_id": "ding-1"},
        )

    assert response_json(response) == {"success": True}
    task.assert_called_once_with(
        bot_id=7,
        msg_id="msg-1",
        text_content="check database",
        sender_id="user-1",
        webhook_url="https://oapi.dingtalk.com/robot/send",
        config={"client_secret": "secret", "node_id": "ding-1"},
    )


@pytest.mark.asyncio
async def test_dingtalk_stream_callback_returns_text_reply():
    handler = dingtalk.DingTalkStreamCallbackHandler(
        7,
        NS(),
        {"node_id": "ding-1"},
    )
    with patch.object(
        handler.utils,
        "execute_chatflow_with_message",
        return_value="all healthy",
    ) as execute:
        status, reply = await handler.process(
            NS(
                data={
                    "msgtype": "text",
                    "text": {"content": "inspect"},
                    "senderStaffId": "user-1",
                }
            )
        )

    assert status == dingtalk.dingtalk_stream.AckMessage.STATUS_OK
    assert reply == {
        "msgtype": "text",
        "text": {"content": "all healthy"},
    }
    execute.assert_called_once_with(
        handler.bot_chat_flow,
        "ding-1",
        "inspect",
        "user-1",
        is_third_party=True,
    )


class ExternalWechatClient:
    instances = []

    def __init__(self, appid, secret):
        self.appid = appid
        self.secret = secret
        self.sent = []
        self.message = NS(send_text=self.sent_message)
        self.__class__.instances.append(self)

    def sent_message(self, openid, text):
        self.sent.append((openid, text))


def test_wechat_official_splits_long_customer_service_messages():
    ExternalWechatClient.instances = []
    utils = wechat.WechatOfficialChatFlowUtils(bot_id=8)
    with (
        patch.object(wechat, "WeChatClient", ExternalWechatClient),
        patch.object(wechat.time, "sleep") as sleep,
    ):
        utils.send_message_chunks(
            "openid-1",
            "a" * 1801,
            "appid",
            "secret",
        )

    client = ExternalWechatClient.instances[0]
    assert [len(text) for _openid, text in client.sent] == [1800, 1]
    assert all(openid == "openid-1" for openid, _text in client.sent)
    assert sleep.call_count == 2


def test_wechat_official_node_config_and_url_verification():
    utils = wechat.WechatOfficialChatFlowUtils(bot_id=8)
    flow = NS(
        flow_json={
            "nodes": [
                {
                    "id": "wechat-1",
                    "type": "wechat_official",
                    "data": {
                        "config": {
                            "token": "token",
                            "appid": "appid",
                            "secret": "secret",
                            "aes_key": "a" * 43,
                        }
                    },
                }
            ]
        }
    )

    config, error = utils.get_wechat_official_node_config(flow)
    with patch.object(wechat, "check_signature") as verify:
        verified = utils.handle_url_verification(
            "signature",
            "timestamp",
            "nonce",
            "echo",
            "token",
            "aes",
            "appid",
        )

    assert error is None
    assert config["node_id"] == "wechat-1"
    assert verified.content == b"echo"
    verify.assert_called_once_with(
        "token",
        "signature",
        "timestamp",
        "nonce",
    )
    assert utils.handle_url_verification(
        "signature",
        "timestamp",
        "nonce",
        "",
        "token",
        "aes",
        "appid",
    ).content == b"fail"


def test_wechat_official_message_dispatches_celery_after_decrypt():
    utils = wechat.WechatOfficialChatFlowUtils(bot_id=8)
    request = NS(
        GET={
            "signature": "signature",
            "timestamp": "1710000000",
            "nonce": "nonce",
        },
        body=(
            b"<xml><Encrypt><![CDATA[encrypted-message]]></Encrypt></xml>"
        ),
    )
    message = NS(
        type="text",
        content="inspect database",
        source="openid-1",
        id="msg-2",
    )
    task = MagicMock()
    config = {
        "aes_key": "a" * 43,
        "appid": "appid",
        "secret": "secret",
    }
    with (
        patch.object(utils, "decrypt", return_value=b"decrypted"),
        patch.object(wechat, "parse_message", return_value=message),
        patch.object(utils, "is_message_processed", return_value=False),
        patch.object(wechat.process_wechat_official_message, "delay", task),
    ):
        response = utils.handle_wechat_message(request, config, NS())

    assert response.content == b"success"
    task.assert_called_once_with(
        8,
        "msg-2",
        "inspect database",
        "openid-1",
        config,
    )
