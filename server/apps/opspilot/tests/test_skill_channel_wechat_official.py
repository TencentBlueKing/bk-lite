"""智能体微信公众号渠道测试。"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.services.skill_channel_wechat_official import SkillChannelWechatOfficialUtils, normalize_wechat_official_channel_config
from apps.opspilot.tasks import process_skill_channel_wechat_official_message

pytestmark = pytest.mark.django_db

_REQUIRED = {"token": "tok", "appid": "app", "secret": "sec", "aes_key": "aes" + "0" * 40}


def _skill(**kwargs):
    defaults = {"name": "official-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _channel(skill, enabled=True, config=None):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.WECHAT_OFFICIAL,
        enabled=enabled,
        usage_team=[1],
        channel_config=config or dict(_REQUIRED),
    )


class TestNormalize:
    def test_alias(self):
        cfg = normalize_wechat_official_channel_config({"token": "t", "appid": "a", "secret": "s", "encodingAESKey": "k"})
        assert cfg["aes_key"] == "k"


class TestOfficialHttp:
    def test_disabled_403(self):
        ch = _channel(_skill(), enabled=False)
        assert opspilot_views.execute_skill_channel_im(RequestFactory().get("/"), ch.id, SkillChannelChoices.WECHAT_OFFICIAL).status_code == 403

    def test_url_verification(self):
        ch = _channel(_skill())
        req = RequestFactory().get("/", {"signature": "s", "timestamp": "1", "nonce": "n", "echostr": "echo"})
        with patch.object(SkillChannelWechatOfficialUtils, "handle_url_verification", return_value=MagicMock(content=b"echo")) as verify:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.WECHAT_OFFICIAL)
        assert resp.content == b"echo"
        verify.assert_called_once()

    def test_post_dispatches(self):
        ch = _channel(_skill())
        req = RequestFactory().post(
            "/", data=b"<xml><Encrypt>x</Encrypt></xml>", content_type="application/xml", QUERY_STRING="signature=s&timestamp=1&nonce=n"
        )
        msg = MagicMock(type="text", content="hi", source="openid1", id="m1")
        with patch.object(SkillChannelWechatOfficialUtils, "decrypt", return_value="<xml/>"), patch(
            "apps.opspilot.services.skill_channel_wechat_official.parse_message", return_value=msg
        ), patch.object(SkillChannelWechatOfficialUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_wechat_official_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.WECHAT_OFFICIAL)
        assert resp.content == b"success"
        delay.assert_called_once()
        assert delay.call_args.kwargs["message"] == "hi"
        assert delay.call_args.kwargs["sender_id"] == "openid1"


class TestOfficialTasks:
    def test_runs_and_replies(self):
        ch = _channel(_skill())
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync", return_value="答"
        ), patch.object(SkillChannelWechatOfficialUtils, "send_reply") as send, patch.object(
            SkillChannelWechatOfficialUtils, "mark_message_completed"
        ) as completed:
            process_skill_channel_wechat_official_message.run(ch.id, "m1", "问", "openid1", dict(_REQUIRED))
        send.assert_called_once()
        assert send.call_args.args[0] == "答"
        completed.assert_called_once_with("m1")

    def test_skips_offline(self):
        ch = _channel(_skill(), enabled=False)
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync"
        ) as execute:
            out = process_skill_channel_wechat_official_message.run(ch.id, "m1", "问", "u", dict(_REQUIRED))
        assert out["skipped"] is True
        execute.assert_not_called()
