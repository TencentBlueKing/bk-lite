"""智能体钉钉 HTTP 渠道测试。"""

import json
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.services.skill_channel_dingtalk import SkillChannelDingtalkUtils, normalize_dingtalk_channel_config
from apps.opspilot.tasks import process_skill_channel_dingtalk_message

pytestmark = pytest.mark.django_db

_REQUIRED = {"client_id": "cid", "client_secret": "csec"}


def _skill(**kwargs):
    defaults = {"name": "ding-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _channel(skill, enabled=True, config=None):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.DINGTALK,
        enabled=enabled,
        usage_team=[1],
        channel_config=config or dict(_REQUIRED),
    )


class TestNormalize:
    def test_app_key_alias(self):
        cfg = normalize_dingtalk_channel_config({"appKey": "k", "appSecret": "s"})
        assert cfg["client_id"] == "k"
        assert cfg["client_secret"] == "s"


class TestDingtalkHttp:
    def test_disabled_403(self):
        ch = _channel(_skill(), enabled=False)
        assert opspilot_views.execute_skill_channel_im(RequestFactory().get("/"), ch.id, SkillChannelChoices.DINGTALK).status_code == 403

    def test_get_success(self):
        ch = _channel(_skill())
        resp = opspilot_views.execute_skill_channel_im(RequestFactory().get("/"), ch.id, SkillChannelChoices.DINGTALK)
        assert resp.status_code == 200
        assert resp.content == b"success"

    def test_post_text_dispatches(self):
        ch = _channel(_skill())
        body = {
            "msgtype": "text",
            "text": {"content": "你好"},
            "senderStaffId": "u1",
            "msgId": "m1",
            "sessionWebhook": "https://oapi.dingtalk.com/robot/send?token=x",
        }
        req = RequestFactory().post("/", data=json.dumps(body), content_type="application/json")
        with patch.object(SkillChannelDingtalkUtils, "is_message_processed", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_dingtalk_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.DINGTALK)
        assert resp.status_code == 200
        delay.assert_called_once()
        kwargs = delay.call_args.kwargs
        assert kwargs["text_content"] == "你好"
        assert kwargs["sender_id"] == "u1"
        assert kwargs["webhook_url"].startswith("https://")

    def test_invalid_signature_rejects(self):
        ch = _channel(_skill())
        body = {"msgtype": "text", "text": {"content": "hi"}, "senderStaffId": "u1", "msgId": "m1"}
        req = RequestFactory().post(
            "/",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_TIMESTAMP="1",
            HTTP_SIGN="bad",
        )
        with patch.object(SkillChannelDingtalkUtils, "verify_signature", return_value=False), patch(
            "apps.opspilot.tasks.process_skill_channel_dingtalk_message.delay"
        ) as delay:
            resp = opspilot_views.execute_skill_channel_im(req, ch.id, SkillChannelChoices.DINGTALK)
        assert json.loads(resp.content)["success"] is False
        delay.assert_not_called()


class TestDingtalkTasks:
    def test_runs_markdown_reply(self):
        ch = _channel(_skill())
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync", return_value="答"
        ), patch.object(SkillChannelDingtalkUtils, "send_message") as send, patch.object(
            SkillChannelDingtalkUtils, "mark_message_completed"
        ) as completed:
            process_skill_channel_dingtalk_message.run(ch.id, "m1", "问", "u1", "https://example.com/hook", dict(_REQUIRED))
        send.assert_called_once()
        assert send.call_args.args[0] == "https://example.com/hook"
        assert send.call_args.args[1] == "markdown"
        completed.assert_called_once_with("m1")

    def test_skips_offline(self):
        ch = _channel(_skill(), enabled=False)
        with patch("apps.opspilot.tasks._run_in_native_thread", side_effect=lambda f, *a, **k: f(*a, **k)), patch(
            "apps.opspilot.services.skill_channel_chat_service.execute_skill_channel_im_sync"
        ) as execute:
            out = process_skill_channel_dingtalk_message.run(ch.id, "m1", "问", "u", "", dict(_REQUIRED))
        assert out["skipped"] is True
        execute.assert_not_called()
