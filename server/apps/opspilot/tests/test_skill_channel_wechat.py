"""智能体企微应用渠道：协议复用 + 单 Agent 异步回覆。"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.services.skill_channel_wechat import SkillChannelWechatUtils, normalize_wechat_channel_config
from apps.opspilot.tasks import process_skill_channel_wechat_message

pytestmark = pytest.mark.django_db

_REQUIRED = {
    "token": "tok",
    "aes_key": "aes" + "0" * 40,
    "corp_id": "corp",
    "agent_id": "1001",
    "secret": "sec",
}


def _skill(**kwargs):
    defaults = {"name": "wechat-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _wechat_channel(skill, enabled=True, config=None):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.ENTERPRISE_WECHAT,
        enabled=enabled,
        usage_team=[1],
        channel_config=config or dict(_REQUIRED),
    )


class TestNormalizeConfig:
    def test_maps_encoding_aes_key_alias(self):
        cfg = normalize_wechat_channel_config({"token": "t", "encodingAESKey": "k", "corp_id": "c", "agent_id": "1", "secret": "s"})
        assert cfg["aes_key"] == "k"
        assert cfg["token"] == "t"

    def test_keeps_bot_field_names(self):
        cfg = normalize_wechat_channel_config(_REQUIRED)
        assert cfg["aes_key"] == _REQUIRED["aes_key"]
        assert cfg["corp_id"] == "corp"


class TestWechatHttp:
    def test_disabled_returns_403(self):
        skill = _skill()
        ch = _wechat_channel(skill, enabled=False)
        resp = opspilot_views.execute_skill_channel_im(RequestFactory().get("/"), ch.id, SkillChannelChoices.ENTERPRISE_WECHAT)
        assert resp.status_code == 403

    def test_url_verification(self):
        skill = _skill()
        ch = _wechat_channel(skill)
        req = RequestFactory().get("/", {"msg_signature": "s", "timestamp": "1", "nonce": "n", "echostr": "e"})
        with patch("apps.opspilot.services.skill_channel_wechat.WeChatCrypto") as crypto_cls, patch.object(
            SkillChannelWechatUtils, "handle_url_verification", return_value=MagicMock(status_code=200, content=b"echo")
        ) as verify:
            crypto_cls.return_value = MagicMock()
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT)
        assert resp.content == b"echo"
        verify.assert_called_once()

    def test_post_text_dispatches_task(self):
        skill = _skill()
        ch = _wechat_channel(skill)
        req = RequestFactory().post(
            "/",
            data=b"<xml/>",
            content_type="application/xml",
            QUERY_STRING="msg_signature=s&timestamp=1&nonce=n",
        )
        msg = MagicMock(type="text", content="你好", source="user-1", id="m1")
        with patch("apps.opspilot.services.skill_channel_wechat.WeChatCrypto") as crypto_cls, patch.object(
            SkillChannelWechatUtils, "parse_message", return_value=msg
        ), patch.object(SkillChannelWechatUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_wechat_message.delay"
        ) as delay:
            crypto_cls.return_value.decrypt_message.return_value = "<xml/>"
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT)

        assert resp.content == b"success"
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        assert kwargs["channel_id"] == ch.id
        assert kwargs["msg_id"] == "m1"
        assert kwargs["message"] == "你好"
        assert kwargs["sender_id"] == "user-1"

    def test_post_decrypt_error_acks(self):
        skill = _skill()
        ch = _wechat_channel(skill)
        req = RequestFactory().post("/", data=b"x", content_type="application/xml", QUERY_STRING="msg_signature=s&timestamp=1&nonce=n")
        with patch("apps.opspilot.services.skill_channel_wechat.WeChatCrypto") as crypto_cls, patch(
            "apps.opspilot.tasks.process_skill_channel_wechat_message.delay"
        ) as delay:
            crypto_cls.return_value.decrypt_message.side_effect = RuntimeError("bad")
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT)
        assert resp.content == b"success"
        delay.assert_not_called()

    def test_non_text_acks_without_dispatch(self):
        skill = _skill()
        ch = _wechat_channel(skill)
        req = RequestFactory().post("/", data=b"x", content_type="application/xml", QUERY_STRING="msg_signature=s&timestamp=1&nonce=n")
        msg = MagicMock(type="image", content="", source="u", id="m2")
        with patch("apps.opspilot.services.skill_channel_wechat.WeChatCrypto") as crypto_cls, patch.object(
            SkillChannelWechatUtils, "parse_message", return_value=msg
        ), patch("apps.opspilot.tasks.process_skill_channel_wechat_message.delay") as delay:
            crypto_cls.return_value.decrypt_message.return_value = "<xml/>"
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT)
        assert resp.content == b"success"
        delay.assert_not_called()


class TestWechatTasks:
    def test_message_task_runs_skill_and_replies(self):
        skill = _skill()
        ch = _wechat_channel(skill)
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync",
            return_value="答",
        ) as execute, patch.object(SkillChannelWechatUtils, "send_reply") as send, patch.object(
            SkillChannelWechatUtils, "mark_message_completed"
        ) as completed, patch.object(
            SkillChannelWechatUtils, "mark_message_failed"
        ) as failed:
            process_skill_channel_wechat_message.run(ch.id, "m1", "问", "user-1", dict(_REQUIRED))

        execute.assert_called_once()
        assert execute.call_args.kwargs["channel"].id == ch.id
        assert execute.call_args.kwargs["user_message"] == "问"
        send.assert_called_once()
        assert send.call_args.args[0] == "答"
        assert send.call_args.args[1] == "user-1"
        completed.assert_called_once_with("m1")
        failed.assert_not_called()

    def test_message_task_skips_when_offline(self):
        skill = _skill()
        ch = _wechat_channel(skill, enabled=False)
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync"
        ) as execute, patch.object(SkillChannelWechatUtils, "send_reply") as send:
            out = process_skill_channel_wechat_message.run(ch.id, "m1", "问", "u", dict(_REQUIRED))
        assert out["skipped"] is True
        execute.assert_not_called()
        send.assert_not_called()
