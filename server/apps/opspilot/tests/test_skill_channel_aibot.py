"""智能体企微 aibot 渠道：协议复用 + 单 Agent 异步回覆。"""

import logging
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.core.logger import safe_log_value
from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation
from apps.opspilot.services.skill_channel_aibot import (
    SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE,
    SkillChannelAibotUtils,
    normalize_aibot_channel_config,
)
from apps.opspilot.tasks import process_skill_channel_aibot_message, process_skill_channel_aibot_reply
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCryptoError
from apps.opspilot.views.skill_channel import SKILL_CHANNEL_IM_ACCEPTED_TEMPLATE

pytestmark = pytest.mark.django_db


def _skill(**kwargs):
    defaults = {"name": "aibot-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


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
        assert resp.content == b"success"
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        assert kwargs["channel_id"] == ch.id
        assert kwargs["msg_id"] == "m1"
        assert kwargs["sender_id"] == "user-1"
        assert kwargs["message"]["last_message"] == "查询 CPU"
        assert kwargs["config"]["response_url"] == "https://example.com/response"

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
        assert resp.content == b"success"
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
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
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

    def test_message_task_skips_when_offline(self):
        skill = _skill()
        ch = _aibot_channel(skill, enabled=False)
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
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
        with patch("apps.opspilot.services.chat_service.chat_service.chat", return_value={"content": "答"}):
            text = execute_skill_channel_im_sync(
                channel=ch,
                user_message="问",
                external_user_id="user-1",
                session_id="chat-1",
            )
        assert text == "答"
        conv = SkillConversation.objects.get(channel=ch, external_user_id="user-1")
        roles = list(conv.messages.order_by("id").values_list("role", flat=True))
        assert roles == ["user", "assistant"]
        assert list(conv.messages.order_by("id").values_list("content", flat=True)) == ["问", "答"]
