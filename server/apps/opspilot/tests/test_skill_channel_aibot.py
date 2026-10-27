"""智能体企微 aibot 渠道：协议复用 + 单 Agent 异步回覆。"""

import json
import logging
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.core.logger import safe_log_value
from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation
from apps.opspilot.services.skill_channel_aibot import (
    SHORT_CONNECTION_IMAGE_REPLY_LOG,
    SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE,
    SkillChannelAibotUtils,
    append_short_connection_file_links,
    claim_short_connection_delivery,
    finish_short_connection_stream,
    normalize_aibot_channel_config,
    open_short_connection_stream,
    short_connection_stream_payload,
)
from apps.opspilot.services.skill_channel_im_media import ImImage
from apps.opspilot.tasks import process_skill_channel_aibot_message, process_skill_channel_aibot_reply
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError
from apps.opspilot.views.skill_channel import SKILL_CHANNEL_IM_ACCEPTED_TEMPLATE

pytestmark = pytest.mark.django_db


def _skill(**kwargs):
    defaults = {"name": "aibot-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _decrypt_passive(resp, token="tok", encoding_aes_key=None):
    body = json.loads(resp.content)
    crypto = EnterpriseWechatAibotCrypto(token=token, encoding_aes_key=encoding_aes_key or ("0" * 43))
    return crypto.decrypt_callback(
        body["msgsignature"],
        body["timestamp"],
        body["nonce"],
        json.dumps({"encrypt": body["encrypt"]}).encode("utf-8"),
    )


def _aibot_channel(skill, enabled=True, config=None):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
        enabled=enabled,
        usage_team=[1],
        channel_config=config
        or {
            "connectionMode": "webhook",
            "webhook": {"token": "tok", "encodingAESKey": "0" * 43, "aibotid": "bot-a"},
        },
    )


class TestNormalizeConfig:
    def test_wraps_flat_config(self):
        assert normalize_aibot_channel_config({"token": "t", "encodingAESKey": "k", "aibotid": "a"}) == {
            "connectionMode": "webhook",
            "webhook": {"token": "t", "encodingAESKey": "k"},
        }

    def test_keeps_bot_shape(self):
        cfg = {"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}
        assert normalize_aibot_channel_config(cfg)["webhook"]["token"] == "t"

    def test_keeps_long_connection_credentials(self):
        cfg = {"connectionMode": "websocket", "websocket": {"botId": " bot-1 ", "secret": " sec "}}
        normalized = normalize_aibot_channel_config(cfg)
        assert normalized["connectionMode"] == "websocket"
        assert normalized["websocket"] == {"botId": "bot-1", "secret": "sec"}


class TestAibotHttp:
    def test_wecom_callback_skips_login_token(self):
        from apps.core.middlewares.auth_middleware import AuthMiddleware

        assert getattr(opspilot_views.execute_skill_channel_im, "api_exempt", False) is True
        mw = AuthMiddleware(get_response=lambda r: None)
        req = RequestFactory().get("/api/v1/opspilot/skill_channel/1/enterprise_wechat_aibot/")
        assert not req.META.get("HTTP_AUTHORIZATION")
        assert mw.process_view(req, opspilot_views.execute_skill_channel_im, [], {}) is None

    def test_disabled_returns_403(self):
        skill = _skill()
        ch = _aibot_channel(skill, enabled=False)
        req = RequestFactory().get("/")
        resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.status_code == 403

    def test_url_verification_uses_channel_config(self):
        skill = _skill()
        ch = _aibot_channel(skill, config={"token": "tok", "encodingAESKey": "0" * 43})
        req = RequestFactory().get("/", {"msg_signature": "s", "timestamp": "1", "nonce": "n", "echostr": "e"})
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
            return_value="plain",
        ):
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.status_code == 200
        assert resp.content == b"plain"

    def test_url_verification_logs_accepted_without_query_secrets(self, caplog):
        token_sentinel = "WECOM_TOKEN_SENTINEL_do_not_log"
        signature_sentinel = "MSG_SIGNATURE_SENTINEL_do_not_log"
        echo_sentinel = "ECHOSTR_SENTINEL_do_not_log"
        skill = _skill()
        ch = _aibot_channel(
            skill,
            config={"token": token_sentinel, "encodingAESKey": "0" * 43},
        )
        req = RequestFactory().get(
            "/",
            {
                "msg_signature": signature_sentinel,
                "timestamp": "1",
                "nonce": "n",
                "echostr": echo_sentinel,
            },
        )
        caplog.set_level(logging.INFO, logger="opspilot")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
            return_value="plain",
        ):
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.status_code == 200
        assert resp.content == b"plain"

        records = [record for record in caplog.records if record.msg == SKILL_CHANNEL_IM_ACCEPTED_TEMPLATE]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.INFO
        assert record.args == (
            ch.id,
            safe_log_value(SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT),
            safe_log_value("GET"),
        )
        rendered = record.getMessage()
        formatted = logging.Formatter().format(record)
        expected = SKILL_CHANNEL_IM_ACCEPTED_TEMPLATE % (
            ch.id,
            safe_log_value(SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT),
            safe_log_value("GET"),
        )
        assert rendered == expected
        for text in (rendered, formatted, caplog.text):
            assert token_sentinel not in text
            assert signature_sentinel not in text
            assert echo_sentinel not in text

    def test_post_text_dispatches_skill_aibot_task(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        message = {
            "msgid": "m1",
            "aibotid": "bot-a",
            "chatid": "chat-1",
            "from": {"userid": "user-1"},
            "response_url": "https://example.com/response",
            "msgtype": "text",
            "text": {"content": "@机器人 查询 CPU"},
        }
        req = RequestFactory().post(
            "/",
            data=b'{"encrypt":"x"}',
            content_type="application/json",
            QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
        )
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch.object(SkillChannelAibotUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_aibot_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)

        assert resp.status_code == 200
        payload = _decrypt_passive(resp)
        assert payload["stream"]["finish"] is False
        assert payload["stream"]["content"] == "正在处理"
        assert "![" not in payload["stream"]["content"]
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        assert kwargs["channel_id"] == ch.id
        assert kwargs["msg_id"] == "m1"
        assert kwargs["sender_id"] == "user-1"
        assert kwargs["message"]["last_message"] == "查询 CPU"
        assert kwargs["config"]["response_url"] == "https://example.com/response"
        assert kwargs["config"]["download_origin"] == "http://testserver"
        assert kwargs["config"]["stream_id"] == payload["stream"]["id"]

    def test_post_ignores_stored_aibotid(self):
        skill = _skill()
        ch = _aibot_channel(
            skill,
            config={
                "connectionMode": "webhook",
                "webhook": {"token": "tok", "encodingAESKey": "0" * 43, "aibotid": "expected"},
            },
        )
        message = {
            "msgid": "m-ignore-aibot",
            "aibotid": "actual",
            "from": {"userid": "user-1"},
            "msgtype": "text",
            "text": {"content": "hi"},
        }
        req = RequestFactory().post("/", data=b'{"encrypt":"x"}', content_type="application/json")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch.object(SkillChannelAibotUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_aibot_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.status_code == 200
        assert _decrypt_passive(resp)["stream"]["finish"] is False
        delay.assert_called_once()
        assert delay.call_args.kwargs["msg_id"] == "m-ignore-aibot"

    def test_post_decrypt_error_acks_without_dispatch(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        req = RequestFactory().post("/", data=b"{}", content_type="application/json")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            side_effect=EnterpriseWechatAibotCryptoError("bad"),
        ), patch("apps.opspilot.tasks.process_skill_channel_aibot_message.delay") as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.content == b"success"
        delay.assert_not_called()

    def test_post_invalid_signature_logs_without_secrets_or_traceback(self, caplog):
        import base64
        import hashlib
        import json
        import struct

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        token_sentinel = "WECOM_TOKEN_SENTINEL_do_not_log"
        encrypt_sentinel = "WECOM_ENCRYPT_SENTINEL"
        encoding_aes_key = base64.b64encode(b"0" * 32).decode("utf-8").rstrip("=")
        key = base64.b64decode(f"{encoding_aes_key}=")
        content = json.dumps({"msgid": "m1"}, separators=(",", ":")).encode("utf-8")
        plain = b"1" * 16 + struct.pack("!I", len(content)) + content
        pad = 32 - (len(plain) % 32)
        plain = plain + bytes([pad]) * pad
        cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16]))
        encrypted = base64.b64encode(cipher.encryptor().update(plain) + cipher.encryptor().finalize()).decode("utf-8")
        signature = hashlib.sha1("".join(sorted([token_sentinel, "1", "n", encrypted])).encode("utf-8")).hexdigest()

        skill = _skill()
        ch = _aibot_channel(
            skill,
            config={
                "connectionMode": "webhook",
                "webhook": {"token": "wrong-token", "encodingAESKey": encoding_aes_key},
            },
        )
        req = RequestFactory().post(
            "/",
            data=json.dumps({"encrypt": encrypted, "note": encrypt_sentinel}).encode("utf-8"),
            content_type="application/json",
            QUERY_STRING=f"msg_signature={signature}&timestamp=1&nonce=n",
        )
        caplog.set_level(logging.INFO, logger="opspilot")
        with patch("apps.opspilot.tasks.process_skill_channel_aibot_message.delay") as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)

        assert resp.status_code == 200
        assert resp.content == b"success"
        delay.assert_not_called()
        records = [record for record in caplog.records if record.msg == SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE]
        assert len(records) == 1
        record = records[0]
        assert record.levelno == logging.WARNING
        assert record.exc_info is None
        assert record.args == (ch.id, "invalid signature", True, True, True, len("wrong-token"))
        rendered = record.getMessage()
        formatted = logging.Formatter().format(record)
        for text in (rendered, formatted, caplog.text):
            assert token_sentinel not in text
            assert encrypt_sentinel not in text
            assert encrypted not in text
            assert signature not in text

    def test_post_duplicate_skips_dispatch(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        message = {"msgid": "m1", "aibotid": "bot-a", "msgtype": "text", "text": {"content": "hi"}}
        req = RequestFactory().post("/", data=b"{}", content_type="application/json")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch.object(SkillChannelAibotUtils, "is_message_processed", return_value=True), patch(
            "apps.opspilot.tasks.process_skill_channel_aibot_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.content == b"success"
        delay.assert_not_called()

    def test_non_text_queues_tip_reply(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        message = {
            "msgid": "m2",
            "aibotid": "bot-a",
            "msgtype": "image",
            "response_url": "https://example.com/r",
        }
        req = RequestFactory().post("/", data=b"{}", content_type="application/json")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch.object(SkillChannelAibotUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_aibot_reply.delay"
        ) as reply_delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp.content == b"success"
        reply_delay.assert_called_once_with(ch.id, "m2", "https://example.com/r", "当前仅支持文本消息")

    def test_stream_poll_sends_image_bytes_and_strips_url(self, caplog, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "aibot-stream-poll"}}
        skill = _skill()
        ch = _aibot_channel(skill)
        image_url = "https://blocked.example/wiki.png?sig=SENTINEL_IMAGE_URL"
        png = b"\x89PNG\r\n\x1a\n" + b"pixels"
        image_item = {"msgtype": "image", "image": {"base64": "cGl4", "md5": "abc"}}
        open_short_connection_stream(ch.id, "stream-1", "https://example.com/response")
        image = ImImage(alt="图", source_url=image_url, public_url=image_url, content=png, content_type="image/png")
        message = {"msgid": "poll-1", "msgtype": "stream", "stream": {"id": "stream-1"}}
        req = RequestFactory().post(
            "/",
            data=b"{}",
            content_type="application/json",
            QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
        )
        caplog.set_level(logging.INFO, logger="opspilot")
        with patch(
            "apps.opspilot.services.skill_channel_aibot.wecom_short_connection_outbound",
            return_value=("说明", [image_item]),
        ) as outbound, patch(
            "apps.opspilot.services.skill_channel_im_media.prepare_im_markdown",
            side_effect=AssertionError("poll must not download images"),
        ):
            finish_short_connection_stream(ch.id, "stream-1", f"说明\n\n![图]({image_url})")
            outbound.assert_called_once()
            assert image_url in outbound.call_args.args[0]
            with patch(
                "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
                return_value=message,
            ):
                resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
                again = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)

        assert outbound.call_count == 1
        assert claim_short_connection_delivery(ch.id, "stream-1") is False
        payload = _decrypt_passive(resp)
        assert payload["stream"]["finish"] is True
        assert payload["stream"]["content"] == "说明"
        assert payload["stream"]["msg_item"] == [image_item]
        assert "msg_item" not in _decrypt_passive(again)["stream"]
        assert image_url not in resp.content.decode("utf-8")
        rendered = " ".join(record.getMessage() for record in caplog.records)
        formatted = " ".join(logging.Formatter().format(record) for record in caplog.records)
        assert image_url not in rendered
        assert "SENTINEL_IMAGE_URL" not in rendered
        assert "cGl4" not in rendered
        assert "cGl4" not in formatted
        image_logs = [record for record in caplog.records if record.msg == SHORT_CONNECTION_IMAGE_REPLY_LOG]
        assert len(image_logs) == 1
        assert image_logs[0].args == (ch.id, 1)
        assert image.content == png

    def test_encrypt_failure_releases_claim_and_keeps_images_for_fallback(self, caplog, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "aibot-stream-encrypt"}}
        skill = _skill()
        ch = _aibot_channel(skill)
        image_url = "https://blocked.example/wiki.png?sig=SENTINEL_IMAGE_URL"
        image_item = {"msgtype": "image", "image": {"base64": "cGl4", "md5": "abc"}}
        open_short_connection_stream(ch.id, "stream-1", "https://example.com/response")
        finish_short_connection_stream(
            ch.id,
            "stream-1",
            f"说明\n\n![图]({image_url})",
            visible="说明",
            msg_items=[image_item],
        )
        message = {"msgid": "poll-enc", "msgtype": "stream", "stream": {"id": "stream-1"}}
        req = RequestFactory().post(
            "/",
            data=b"{}",
            content_type="application/json",
            QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
        )
        caplog.set_level(logging.INFO, logger="opspilot")
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.encrypt_reply",
            side_effect=EnterpriseWechatAibotCryptoError("encrypt-failed"),
        ), patch(
            "apps.opspilot.services.skill_channel_im_media.prepare_im_markdown",
            side_effect=AssertionError("encrypt failure must not download images"),
        ):
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)

        assert resp.content == b"success"
        rendered = " ".join(record.getMessage() for record in caplog.records)
        assert image_url not in rendered
        assert "cGl4" not in rendered
        with patch.object(SkillChannelAibotUtils, "send_markdown_reply") as send, patch.object(
            SkillChannelAibotUtils, "mark_message_completed"
        ) as completed:
            process_skill_channel_aibot_reply.run(ch.id, "poll-enc", "https://example.com/response", "说明", "stream-1")
        send.assert_called_once_with("https://example.com/response", "说明")
        completed.assert_called_once_with("poll-enc")

        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch(
            "apps.opspilot.services.skill_channel_im_media.prepare_im_markdown",
            side_effect=AssertionError("retry poll must not download images"),
        ):
            retried = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert _decrypt_passive(retried)["stream"]["msg_item"] == [image_item]
        assert claim_short_connection_delivery(ch.id, "stream-1") is False


class TestAibotTasks:
    def test_message_task_runs_skill_and_enqueues_reply(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        flow_input = {
            "last_message": "查询 CPU",
            "user_id": "user-1",
            "session_id": "chat-1",
            "response_url": "https://example.com/response",
        }
        with patch("apps.opspilot.tasks.channel._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync",
            return_value="CPU 正常",
        ) as execute, patch.object(process_skill_channel_aibot_reply, "delay") as reply_delay, patch.object(
            SkillChannelAibotUtils, "mark_message_failed"
        ) as mark_failed:
            process_skill_channel_aibot_message.run(
                ch.id,
                "m1",
                flow_input,
                "user-1",
                {"response_url": "https://example.com/response"},
            )

        execute.assert_called_once()
        assert execute.call_args.kwargs["channel"].id == ch.id
        assert execute.call_args.kwargs["user_message"] == "查询 CPU"
        assert execute.call_args.kwargs["external_user_id"] == "user-1"
        reply_delay.assert_called_once_with(ch.id, "m1", "https://example.com/response", "CPU 正常")
        mark_failed.assert_not_called()

    def test_message_task_keeps_history_image_and_defers_plain_fallback(self, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "aibot-stream-task"}}
        skill = _skill()
        ch = _aibot_channel(skill)
        image_url = "https://blocked.example/shot.png?sig=KEEP_IN_HISTORY"
        image_item = {"msgtype": "image", "image": {"base64": "YQ==", "md5": "abc"}}
        from django.core.cache import cache

        scheduled = {}

        def _capture_async(*args, **kwargs):
            scheduled["state"] = cache.get(f"skill_channel_aibot_stream:{ch.id}:stream-9")
            scheduled["kwargs"] = kwargs

        with patch("apps.opspilot.tasks.channel._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync",
            return_value=f"见 ![图]({image_url})",
        ), patch(
            "apps.opspilot.services.skill_channel_im_media.wecom_short_connection_outbound",
            return_value=("见", [image_item]),
        ) as outbound, patch.object(
            process_skill_channel_aibot_reply, "apply_async", side_effect=_capture_async
        ) as reply_async, patch.object(
            process_skill_channel_aibot_reply, "delay"
        ) as reply_delay:
            process_skill_channel_aibot_message.run(
                ch.id,
                "m1",
                {"last_message": "看图"},
                "user-1",
                {"response_url": "https://example.com/response", "stream_id": "stream-9"},
            )
        outbound.assert_called_once()
        reply_delay.assert_not_called()
        assert reply_async.call_args.kwargs["args"] == [ch.id, "m1", "https://example.com/response", "见", "stream-9"]
        assert reply_async.call_args.kwargs["countdown"] == 20
        state = cache.get(f"skill_channel_aibot_stream:{ch.id}:stream-9")
        assert state["phase"] == "finished"
        assert image_url in state["reply_text"]
        assert state["visible"] == "见"
        assert state["msg_items"] == [image_item]
        assert state["delivered"] is False
        assert scheduled["state"]["msg_items"] == [image_item]
        assert scheduled["state"]["phase"] == "finished"

    def test_slow_materialize_then_fallback_claim_still_lets_poll_send_images(self, settings):
        settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "aibot-stream-race"}}
        skill = _skill()
        ch = _aibot_channel(skill)
        image_url = "https://blocked.example/shot.png?sig=KEEP_IN_HISTORY"
        image_item = {"msgtype": "image", "image": {"base64": "YQ==", "md5": "abc"}}
        open_short_connection_stream(ch.id, "stream-9", "https://example.com/response")

        def slow_outbound(_text):
            payload, included = short_connection_stream_payload(ch.id, "stream-9")
            assert payload["stream"]["finish"] is False
            assert included is False
            assert claim_short_connection_delivery(ch.id, "stream-9") is False
            return "说明", [image_item]

        with patch("apps.opspilot.tasks.channel._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync",
            return_value=f"说明\n\n![图]({image_url})",
        ), patch(
            "apps.opspilot.services.skill_channel_im_media.wecom_short_connection_outbound",
            side_effect=slow_outbound,
        ) as outbound, patch.object(process_skill_channel_aibot_reply, "apply_async"):
            process_skill_channel_aibot_message.run(
                ch.id,
                "m1",
                {"last_message": "看图"},
                "user-1",
                {"response_url": "https://example.com/response", "stream_id": "stream-9"},
            )
        outbound.assert_called_once()
        assert claim_short_connection_delivery(ch.id, "stream-9") is True
        message = {"msgid": "poll-race", "msgtype": "stream", "stream": {"id": "stream-9"}}
        req = RequestFactory().post(
            "/",
            data=b"{}",
            content_type="application/json",
            QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
        )
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.decrypt_callback",
            return_value=message,
        ), patch(
            "apps.opspilot.services.skill_channel_im_media.prepare_im_markdown",
            side_effect=AssertionError("poll must not download images"),
        ), patch(
            "apps.opspilot.services.skill_channel_aibot.wecom_short_connection_outbound",
            side_effect=AssertionError("poll must not outbound"),
        ):
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        payload = _decrypt_passive(resp)
        assert payload["stream"]["finish"] is True
        assert payload["stream"]["content"] == "说明"
        assert payload["stream"]["msg_item"] == [image_item]
        assert image_url not in resp.content.decode("utf-8")

    def test_message_task_skips_when_offline(self):
        skill = _skill()
        ch = _aibot_channel(skill, enabled=False)
        with patch("apps.opspilot.tasks.channel._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync"
        ) as execute, patch.object(process_skill_channel_aibot_reply, "delay") as reply_delay:
            out = process_skill_channel_aibot_message.run(ch.id, "m1", {"last_message": "x"}, "u", {})
        assert out["skipped"] is True
        execute.assert_not_called()
        reply_delay.assert_not_called()

    def test_reply_task_sends_and_marks_completed(self):
        skill = _skill()
        ch = _aibot_channel(skill)
        with patch.object(SkillChannelAibotUtils, "send_markdown_reply") as send, patch.object(
            SkillChannelAibotUtils, "mark_message_completed"
        ) as completed:
            process_skill_channel_aibot_reply.run(ch.id, "m1", "https://example.com/r", "ok")
        send.assert_called_once_with("https://example.com/r", "ok")
        completed.assert_called_once_with("m1")

    def test_execute_im_sync_persists_messages(self):
        from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync

        skill = _skill()
        ch = _aibot_channel(skill)
        with patch("apps.opspilot.services.chat_service.chat_service.chat", return_value={"content": "答"}) as chat:
            text = execute_skill_channel_im_sync(
                channel=ch,
                user_message="问",
                external_user_id="user-1",
                session_id="chat-1",
            )
        assert text == "答"
        assert chat.call_args.args[0]["reply_language"] == "match_user"
        assert chat.call_args.args[0]["execution_id"]
        conv = SkillConversation.objects.get(channel=ch, external_user_id="user-1")
        roles = list(conv.messages.order_by("id").values_list("role", flat=True))
        assert roles == ["user", "assistant"]
        assert list(conv.messages.order_by("id").values_list("content", flat=True)) == ["问", "答"]

    def test_execute_im_sync_appends_download_link(self, monkeypatch):
        from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync

        skill = _skill()
        ch = _aibot_channel(skill)
        seen = {}

        def fake_append(content, execution_id, channel_id, *, origin):
            seen["execution_id"] = execution_id
            seen["channel_id"] = channel_id
            seen["origin"] = origin
            return content + "\n\n[广州介绍.txt](https://api.example/file)"

        monkeypatch.setattr(
            "apps.opspilot.services.skill_channel_chat_service.append_short_connection_file_links",
            fake_append,
        )
        with patch("apps.opspilot.services.chat_service.chat_service.chat", return_value={"content": "已生成"}):
            text = execute_skill_channel_im_sync(
                channel=ch,
                user_message="生成文档",
                external_user_id="user-1",
                session_id="chat-1",
                download_origin="https://api.example",
            )
        assert seen["execution_id"]
        assert seen["channel_id"] == ch.id
        assert seen["origin"] == "https://api.example"
        assert text.endswith("[广州介绍.txt](https://api.example/file)")
        conv = SkillConversation.objects.get(channel=ch, external_user_id="user-1")
        assert "https://api.example/file" in conv.messages.filter(role="assistant").get().content


def test_append_short_connection_file_links_uses_server_download(monkeypatch):
    asset = type("Asset", (), {"filename": "广州介绍[v1].txt"})()

    class _Query:
        def order_by(self, *args):
            return [asset]

    class _Manager:
        def filter(self, **kwargs):
            assert kwargs == {"execution_id": "exec-1"}
            return _Query()

    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_aibot.WorkflowAttachmentAsset.objects",
        _Manager(),
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_aibot.build_server_attachment_download_path",
        lambda item: "/api/v1/opspilot/bot_mgmt/workflow_attachment/download/tok/",
    )
    text = append_short_connection_file_links("已生成", "exec-1", 7, origin="https://api.example/")
    assert text == "已生成\n\n[广州介绍v1.txt](https://api.example/api/v1/opspilot/bot_mgmt/workflow_attachment/download/tok/)"


def test_append_short_connection_file_links_skips_without_origin(monkeypatch):
    asset = type("Asset", (), {"filename": "a.txt"})()

    class _Query:
        def order_by(self, *args):
            return [asset]

    class _Manager:
        def filter(self, **kwargs):
            return _Query()

    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_aibot.WorkflowAttachmentAsset.objects",
        _Manager(),
    )
    text = append_short_connection_file_links("已生成", "exec-1", 7, origin="")
    assert text == "已生成"
