"""钉钉 Stream 处理器、启动客户端与剩余发信/去重契约。

仅 mock dingtalk_stream / requests / Celery / ChatFlow 引擎边界。
锁定：
- is_valid_dingtalk_url：空 hostname、非法字符、urlparse 异常；
- verify_signature 异常返回 False；
- send_reply 缺 webhook 不发信；
- handle_dingtalk_message 已处理消息跳过投递；
- Stream Event/Callback：非文本、空文本、成功回复、异常状态码；
- start_dingtalk_stream_client：缺凭证、启动成功、启动异常。
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import dingtalk_stream
import pytest
from django.http import JsonResponse

from apps.opspilot.services.dingtalk_chat_flow_utils import (
    DingTalkChatFlowUtils,
    DingTalkStreamCallbackHandler,
    DingTalkStreamEventHandler,
    is_valid_dingtalk_url,
    start_dingtalk_stream_client,
)

pytestmark = pytest.mark.unit


def _utils(bot_id=3):
    u = DingTalkChatFlowUtils.__new__(DingTalkChatFlowUtils)
    u.bot_id = bot_id
    return u


def _req(body, headers=None):
    return SimpleNamespace(
        body=body if isinstance(body, (bytes, str)) else json.dumps(body).encode(),
        headers=headers or {},
    )


class TestUrlAndSignatureRemaining:
    def test_空hostname与非法字符拒绝(self):
        assert is_valid_dingtalk_url("https://") is False
        assert is_valid_dingtalk_url("https://oapi_dingtalk.com") is False

    def test_urlparse异常返回False(self, mocker):
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.urlparse",
            side_effect=ValueError("bad url"),
        )
        assert is_valid_dingtalk_url("https://oapi.dingtalk.com") is False

    def test_验签异常返回False(self):
        utils = _utils()
        assert utils.verify_signature("ts", "sign", None) is False


class TestSendReplyAndHandleSkip:
    def test_缺webhook不发信(self):
        utils = _utils()
        with patch.object(utils, "send_message") as send:
            utils.send_reply("hello", "u1", {})
        send.assert_not_called()

    def test_已处理消息跳过投递(self):
        utils = _utils(8)
        with patch.object(utils, "is_message_processed", return_value=True), patch("apps.opspilot.tasks.process_dingtalk_message.delay") as delay:
            resp = utils.handle_dingtalk_message(
                _req(
                    {
                        "msgtype": "text",
                        "text": {"content": "hi"},
                        "senderStaffId": "u",
                        "msgId": "dup-1",
                    }
                ),
                None,
                {},
            )
        assert isinstance(resp, JsonResponse)
        assert json.loads(resp.content)["success"] is True
        delay.assert_not_called()


class TestStreamHandlers:
    def test_event_handler_ack(self):
        handler = DingTalkStreamEventHandler(9)
        status, msg = asyncio.run(handler.process(SimpleNamespace()))
        assert status == dingtalk_stream.AckMessage.STATUS_OK
        assert msg == "OK"

    def test_callback_非文本与空文本ack(self):
        handler = DingTalkStreamCallbackHandler(1, SimpleNamespace(), {"node_id": "n1"})
        status, msg = asyncio.run(handler.process(SimpleNamespace(data={"msgtype": "image"})))
        assert status == dingtalk_stream.AckMessage.STATUS_OK
        assert msg == "OK"

        status, msg = asyncio.run(handler.process(SimpleNamespace(data={"msgtype": "text", "text": {"content": ""}})))
        assert status == dingtalk_stream.AckMessage.STATUS_OK
        assert msg == "OK"

    def test_callback_成功返回文本回复(self):
        handler = DingTalkStreamCallbackHandler(2, SimpleNamespace(), {"node_id": "n-dt"})
        with patch.object(handler.utils, "execute_chatflow_with_message", return_value="回复内容") as exec_cf:
            status, body = asyncio.run(
                handler.process(
                    SimpleNamespace(
                        data={
                            "msgtype": "text",
                            "text": {"content": "你好"},
                            "senderStaffId": "staff-1",
                        }
                    )
                )
            )
        exec_cf.assert_called_once()
        assert exec_cf.call_args.args[2] == "你好"
        assert exec_cf.call_args.kwargs["is_third_party"] is True
        assert status == dingtalk_stream.AckMessage.STATUS_OK
        assert body == {"msgtype": "text", "text": {"content": "回复内容"}}

    def test_callback_异常返回系统异常码(self):
        handler = DingTalkStreamCallbackHandler(2, SimpleNamespace(), {"node_id": "n-dt"})
        with patch.object(
            handler.utils,
            "execute_chatflow_with_message",
            side_effect=RuntimeError("engine down"),
        ):
            status, msg = asyncio.run(
                handler.process(
                    SimpleNamespace(
                        data={
                            "msgtype": "text",
                            "text": {"content": "hi"},
                            "senderId": "sid",
                        }
                    )
                )
            )
        assert status == dingtalk_stream.AckMessage.STATUS_SYSTEM_EXCEPTION
        assert msg == "engine down"


class TestStartStreamClient:
    def test_缺凭证返回False(self):
        assert start_dingtalk_stream_client(1, None, {}) is False
        assert start_dingtalk_stream_client(1, None, {"client_id": "a"}) is False

    def test_启动成功注册处理器并开线程(self, mocker):
        credential = MagicMock()
        client = MagicMock()
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=credential,
        )
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            return_value=client,
        )
        thread = MagicMock()
        thread_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            return_value=thread,
        )
        ok = start_dingtalk_stream_client(
            7,
            SimpleNamespace(),
            {"client_id": "cid", "client_secret": "sec", "node_id": "n1"},
        )
        assert ok is True
        client.register_all_event_handler.assert_called_once()
        client.register_callback_handler.assert_called_once()
        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs["daemon"] is True
        thread.start.assert_called_once()

    def test_启动异常返回False(self, mocker):
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            side_effect=RuntimeError("auth fail"),
        )
        assert start_dingtalk_stream_client(1, None, {"client_id": "a", "client_secret": "b"}) is False

    def test_线程内start_forever异常被吞(self, mocker):
        client = MagicMock()
        client.start_forever.side_effect = RuntimeError("stream down")
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            return_value=client,
        )

        class _ImmediateThread:
            def __init__(self, target=None, daemon=None):
                self.target = target

            def start(self):
                self.target()

        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            side_effect=lambda target=None, daemon=None: _ImmediateThread(target, daemon),
        )
        assert start_dingtalk_stream_client(4, SimpleNamespace(), {"client_id": "a", "client_secret": "b"}) is True
        client.start_forever.assert_called_once()
