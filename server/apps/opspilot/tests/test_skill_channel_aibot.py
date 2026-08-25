"""智能体企微 aibot 渠道：协议复用 + 单 Agent 异步回覆。"""

from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation
from apps.opspilot.services.skill_channel_aibot import SkillChannelAibotUtils, normalize_aibot_channel_config
from apps.opspilot.tasks import process_skill_channel_aibot_message, process_skill_channel_aibot_reply
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCryptoError

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
            "webhook": {"token": "t", "encodingAESKey": "k", "aibotid": "a"},
        }

    def test_keeps_bot_shape(self):
        cfg = {"connectionMode": "webhook", "webhook": {"token": "t", "encodingAESKey": "k"}}
        assert normalize_aibot_channel_config(cfg)["webhook"]["token"] == "t"


class TestAibotHttp:
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
