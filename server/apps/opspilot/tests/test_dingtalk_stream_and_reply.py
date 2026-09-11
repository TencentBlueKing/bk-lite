"""钉钉 Stream 处理器、启动客户端与剩余发信/去重契约。

仅 mock dingtalk_stream / requests / Celery / ChatFlow 引擎边界。
锁定：
- is_valid_dingtalk_url：空 hostname、非法字符、urlparse 异常；
- verify_signature 异常返回 False；
- send_reply 缺 webhook 不发信；
- handle_dingtalk_message 已处理消息跳过投递；
- Stream Event/Callback：非文本、空文本、成功回复、异常状态码；
- start_dingtalk_stream_client：缺凭证、幂等/并发启动、退出清理、启动异常。
"""
import asyncio
import json
import logging
import time
from threading import Barrier
from threading import Thread as WorkerThread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import dingtalk_stream
import pytest
from django.http import JsonResponse

from apps.opspilot.services import dingtalk_chat_flow_utils as dingtalk_utils_module
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
    @pytest.fixture(autouse=True)
    def _清理活动客户端(self):
        registry = getattr(dingtalk_utils_module, "_dingtalk_stream_clients", None)
        lock = getattr(dingtalk_utils_module, "_dingtalk_stream_clients_lock", None)
        if registry is not None and lock is not None:
            with lock:
                registry.clear()
        yield
        if registry is not None and lock is not None:
            with lock:
                registry.clear()

    def test_缺凭证返回False(self):
        assert start_dingtalk_stream_client(1, None, {}) is False
        assert start_dingtalk_stream_client(1, None, {"client_id": "a"}) is False

    def test_异常配置保持返回False(self):
        assert start_dingtalk_stream_client(1, None, None) is False

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

    def test_同一Bot重复启动只创建一个客户端(self, mocker):
        client = MagicMock()
        credential = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            return_value=client,
        )
        thread = MagicMock()
        thread_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            return_value=thread,
        )

        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}
        results = [start_dingtalk_stream_client(70, SimpleNamespace(), config) for _ in range(25)]

        assert results == [True] * 25
        credential.assert_called_once_with("cid", "sec")
        client_cls.assert_called_once()
        thread_cls.assert_called_once()
        thread.start.assert_called_once()

    def test_同一Bot重复启动仅记录DEBUG(self, mocker, caplog):
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            return_value=MagicMock(),
        )
        mocker.patch("apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread", return_value=MagicMock())
        caplog.set_level(logging.DEBUG, logger="opspilot")

        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}
        assert start_dingtalk_stream_client(70, SimpleNamespace(), config) is True
        assert start_dingtalk_stream_client(70, SimpleNamespace(), config) is True

        records = [record for record in caplog.records if "event=dingtalk_stream_start_reused" in record.getMessage()]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG

    def test_不同Bot分别创建客户端(self, mocker):
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            side_effect=[MagicMock(), MagicMock()],
        )
        stream_threads = [MagicMock(), MagicMock()]
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            side_effect=stream_threads,
        )

        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}
        assert start_dingtalk_stream_client(70, SimpleNamespace(), config) is True
        assert start_dingtalk_stream_client(71, SimpleNamespace(), config) is True

        assert client_cls.call_count == 2
        for stream_thread in stream_threads:
            stream_thread.start.assert_called_once()

    def test_并发启动同一Bot只创建一个客户端(self, mocker):
        client = MagicMock()

        def slow_credential(*_args):
            time.sleep(0.03)
            return MagicMock()

        credential = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            side_effect=slow_credential,
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            return_value=client,
        )
        stream_thread = MagicMock()
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            return_value=stream_thread,
        )
        start_gate = Barrier(8)
        results = []

        def invoke():
            start_gate.wait()
            results.append(
                start_dingtalk_stream_client(
                    71,
                    SimpleNamespace(),
                    {"client_id": "cid", "client_secret": "sec", "node_id": "n1"},
                )
            )

        workers = [WorkerThread(target=invoke) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=2)

        assert len(results) == 8
        assert all(results)
        credential.assert_called_once_with("cid", "sec")
        client_cls.assert_called_once()
        stream_thread.start.assert_called_once()

    def test_客户端线程退出后允许重新启动(self, mocker):
        clients = [MagicMock(), MagicMock()]
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            side_effect=clients,
        )
        threads = []

        class _ControlledThread:
            def __init__(self, target=None, daemon=None):
                self.target = target
                self.daemon = daemon
                threads.append(self)

            def start(self):
                pass

        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            side_effect=_ControlledThread,
        )

        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}
        assert start_dingtalk_stream_client(72, SimpleNamespace(), config) is True
        threads[0].target()
        assert start_dingtalk_stream_client(72, SimpleNamespace(), config) is True

        assert client_cls.call_count == 2
        assert len(threads) == 2

    def test_旧客户端退出不会清理新客户端登记(self, mocker):
        clients = [MagicMock(), MagicMock()]
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            side_effect=clients,
        )
        threads = []

        class _ControlledThread:
            def __init__(self, target=None, daemon=None):
                self.target = target
                threads.append(self)

            def start(self):
                pass

        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            side_effect=_ControlledThread,
        )
        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}

        assert start_dingtalk_stream_client(74, SimpleNamespace(), config) is True
        with dingtalk_utils_module._dingtalk_stream_clients_lock:
            dingtalk_utils_module._dingtalk_stream_clients.pop(74)
        assert start_dingtalk_stream_client(74, SimpleNamespace(), config) is True
        threads[0].target()

        assert dingtalk_utils_module._dingtalk_stream_clients[74] is clients[1]

    def test_线程启动失败会释放登记并允许重试(self, mocker):
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            side_effect=[MagicMock(), MagicMock()],
        )
        failed_thread = MagicMock()
        failed_thread.start.side_effect = RuntimeError("thread start failed")
        running_thread = MagicMock()
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.threading.Thread",
            side_effect=[failed_thread, running_thread],
        )

        config = {"client_id": "cid", "client_secret": "sec", "node_id": "n1"}
        assert start_dingtalk_stream_client(73, SimpleNamespace(), config) is False
        assert start_dingtalk_stream_client(73, SimpleNamespace(), config) is True

        assert client_cls.call_count == 2
        running_thread.start.assert_called_once()

    def test_启动异常返回False且日志脱敏(self, mocker, caplog):
        secret_sentinel = "client_secret=DO_NOT_LOG_5376"
        original_error = RuntimeError(secret_sentinel)
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            side_effect=original_error,
        )
        caplog.set_level(logging.ERROR, logger="opspilot")

        assert start_dingtalk_stream_client(1, None, {"client_id": "a", "client_secret": "b"}) is False

        records = [record for record in caplog.records if "event=dingtalk_stream_start_failed" in record.getMessage()]
        assert len(records) == 1
        record = records[0]
        assert record.msg == "event=dingtalk_stream_start_failed bot_id=%s failed_stage=%s error_type=%s"
        assert record.args == (1, "build_client", "RuntimeError")
        assert record.exc_info is not None
        assert record.exc_info[2] is original_error.__traceback__
        assert original_error.args == (secret_sentinel,)
        assert secret_sentinel not in record.getMessage()
        assert all(secret_sentinel not in str(arg) for arg in record.args)
        assert secret_sentinel not in logging.Formatter().format(record)
        assert secret_sentinel not in caplog.text

    def test_线程内start_forever异常退出后允许重启(self, mocker, caplog):
        secret_sentinel = "access_token=DO_NOT_LOG_RUNTIME_5376"
        original_error = RuntimeError(secret_sentinel)
        clients = [MagicMock(), MagicMock()]
        clients[0].start_forever.side_effect = original_error
        mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.Credential",
            return_value=MagicMock(),
        )
        client_cls = mocker.patch(
            "apps.opspilot.services.dingtalk_chat_flow_utils.dingtalk_stream.DingTalkStreamClient",
            side_effect=clients,
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
        caplog.set_level(logging.ERROR, logger="opspilot")
        config = {"client_id": "a", "client_secret": "b"}
        assert start_dingtalk_stream_client(4, SimpleNamespace(), config) is True
        assert start_dingtalk_stream_client(4, SimpleNamespace(), config) is True

        assert client_cls.call_count == 2
        clients[0].start_forever.assert_called_once()
        clients[1].start_forever.assert_called_once()
        records = [record for record in caplog.records if "event=dingtalk_stream_runtime_failed" in record.getMessage()]
        assert len(records) == 1
        record = records[0]
        assert record.msg == "event=dingtalk_stream_runtime_failed bot_id=%s failed_stage=start_forever error_type=%s"
        assert record.args == (4, "RuntimeError")
        assert record.exc_info is not None
        assert record.exc_info[2] is original_error.__traceback__
        assert original_error.args == (secret_sentinel,)
        assert secret_sentinel not in record.getMessage()
        assert all(secret_sentinel not in str(arg) for arg in record.args)
        assert secret_sentinel not in logging.Formatter().format(record)
        assert secret_sentinel not in caplog.text
