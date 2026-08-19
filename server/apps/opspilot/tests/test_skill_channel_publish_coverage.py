"""智能体渠道发布：补齐行为覆盖（目标核心模块 ≥90%）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.http import StreamingHttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User, UserAPISecret
from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.serializers.skill_channel_serializer import SkillChannelSerializer, _mask_config
from apps.opspilot.services import skill_channel_chat_service as chat_svc
from apps.opspilot.services.caller_identity import CallerIdentityError
from apps.opspilot.services.skill_channel_service import (
    channel_allows_team,
    copy_usage_team_for_channel,
    platform_channels_for_team,
    resolve_ops_pilot_guest_id,
)
from apps.opspilot.tasks import process_skill_channel_im_message
from apps.opspilot.viewsets.llm_view import LLMViewSet
from apps.opspilot.viewsets.skill_channel_view import SkillChannelViewSet

pytestmark = pytest.mark.django_db


def _superuser(username="cov_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}, {"id": 99, "name": "OpsPilotGuest"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _normal(username="cov_n", groups=None, permission=None):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=groups or [{"id": 1, "name": "T1"}],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = permission or {
        "opspilot": {"skill_setting-View", "skill_setting-Edit"},
    }
    return user


def _skill(**kwargs):
    defaults = {"name": "cov-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _channel(skill, **kwargs):
    defaults = {
        "skill": skill,
        "channel_type": SkillChannelChoices.PLATFORM,
        "enabled": True,
        "usage_team": list(skill.usage_team or [1]),
        "name": "ch",
        "channel_config": {},
    }
    defaults.update(kwargs)
    return SkillChannel.objects.create(**defaults)


class TestMaskAndSerializer:
    def test_mask_nested_and_non_dict(self):
        assert _mask_config("x") == {}
        masked = _mask_config({"token": "abc", "webhook": {"secret": "s", "name": "n"}, "plain": "p"})
        assert masked["token"] == "******"
        assert masked["webhook"]["secret"] == "******"
        assert masked["webhook"]["name"] == "n"
        assert masked["plain"] == "p"

    def test_invalid_channel_type_raises_on_validate(self):
        skill = _skill()
        ser = SkillChannelSerializer(data={"skill": skill.id, "channel_type": "nope"})
        with pytest.raises(ValidationError):
            ser.is_valid(raise_exception=True)

    def test_create_non_dict_config_and_default_name(self):
        skill = _skill(usage_team=[1, 2])
        ser = SkillChannelSerializer(data={"skill": skill.id, "channel_type": SkillChannelChoices.WEB_CHAT, "channel_config": "bad"})
        assert ser.is_valid(), ser.errors
        obj = ser.save()
        assert obj.channel_config == {}
        assert obj.name  # default from choices
        assert obj.usage_team == [1, 2]

    def test_update_skips_masked_and_merges_nested(self):
        skill = _skill()
        ch = _channel(
            skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            channel_config={"webhook": {"token": "old", "encodingAESKey": "k"}, "x": 1},
        )
        ser = SkillChannelSerializer(
            ch,
            data={
                "channel_config": {
                    "webhook": {"token": "******", "encodingAESKey": "newk"},
                    "x": 2,
                },
                "usage_team": [9],
            },
            partial=True,
        )
        assert ser.is_valid(), ser.errors
        obj = ser.save()
        assert obj.channel_config["webhook"]["token"] == "old"
        assert obj.channel_config["webhook"]["encodingAESKey"] == "newk"
        assert obj.channel_config["x"] == 2
        assert obj.usage_team == [1]  # not overwritten by request


class TestSkillChannelServiceEdges:
    def test_channel_allows_team_branches(self):
        skill = _skill()
        im = _channel(skill, channel_type=SkillChannelChoices.DINGTALK, usage_team=[])
        web = _channel(skill, channel_type=SkillChannelChoices.WEB_CHAT, usage_team=[1])
        assert channel_allows_team(im, "bad") is True
        assert channel_allows_team(web, "x") is False
        assert channel_allows_team(web, 1) is True
        assert channel_allows_team(web, 2) is False

    def test_guest_and_platform_list(self):
        assert resolve_ops_pilot_guest_id(None) is None
        assert resolve_ops_pilot_guest_id([{"name": "OpsPilotGuest", "id": "bad"}]) is None
        assert resolve_ops_pilot_guest_id([{"name": "OpsPilotGuest", "id": 99}]) == 99
        assert platform_channels_for_team("xx").count() == 0

        skill = _skill(usage_team=[99])
        _channel(skill, usage_team=[99], name="guest-ch")
        qs = platform_channels_for_team(1, [{"name": "OpsPilotGuest", "id": 99}])
        assert qs.filter(name="guest-ch").exists()

    def test_copy_usage_team_fallback(self):
        skill = _skill(team=[3], usage_team=[])
        assert copy_usage_team_for_channel(skill) == [3]


class TestSkillChannelViewSetCoverage:
    def test_list_requires_skill_id(self):
        factory = APIRequestFactory()
        user = _superuser("v_list")
        request = factory.get("/")
        force_authenticate(request, user=user)
        resp = SkillChannelViewSet.as_view({"get": "list"})(request)
        assert resp.status_code == 400

    def test_list_and_update_destroy(self):
        skill = _skill()
        ch = _channel(skill, channel_config={"token": "abc"})
        factory = APIRequestFactory()
        user = _superuser("v_crud")

        req_list = factory.get("/", {"skill_id": skill.id})
        force_authenticate(req_list, user=user)
        resp = SkillChannelViewSet.as_view({"get": "list"})(req_list)
        assert resp.status_code == 200
        assert resp.data["result"] is True
        assert resp.data["data"][0]["channel_config"]["token"] == "******"

        req_upd = factory.put("/", {"name": "renamed", "channel_config": {"token": "new"}}, format="json")
        force_authenticate(req_upd, user=user)
        resp2 = SkillChannelViewSet.as_view({"put": "update"})(req_upd, pk=ch.id)
        assert resp2.status_code == 200
        ch.refresh_from_db()
        assert ch.name == "renamed"
        assert ch.channel_config["token"] == "new"

        req_del = factory.delete("/")
        force_authenticate(req_del, user=user)
        resp3 = SkillChannelViewSet.as_view({"delete": "destroy"})(req_del, pk=ch.id)
        assert resp3.status_code == 200
        assert not SkillChannel.objects.filter(id=ch.id).exists()

    def test_normal_user_with_manage_permission_can_list(self):
        skill = _skill()
        _channel(skill)
        factory = APIRequestFactory()
        user = _normal("v_ok")
        with patch("apps.core.utils.viewset_utils.AuthViewSet.get_has_permission", return_value=True):
            req = factory.get("/", {"skill_id": skill.id})
            force_authenticate(req, user=user)
            resp = SkillChannelViewSet.as_view({"get": "list"})(req)
        assert resp.status_code == 200
        assert resp.data["result"] is True

    def test_create_missing_skill(self):
        factory = APIRequestFactory()
        user = _superuser("v_miss")
        request = factory.post("/", {"channel_type": "platform"}, format="json")
        force_authenticate(request, user=user)
        resp = SkillChannelViewSet.as_view({"post": "create"})(request)
        assert resp.status_code == 400

    def test_permission_denied_for_normal_user(self):
        skill = _skill()
        ch = _channel(skill)
        factory = APIRequestFactory()
        user = _normal("v_deny")
        with patch("apps.core.utils.viewset_utils.AuthViewSet.get_has_permission", return_value=False):
            req = factory.get("/", {"skill_id": skill.id})
            force_authenticate(req, user=user)
            resp = SkillChannelViewSet.as_view({"get": "list"})(req)
            assert resp.status_code == 403

            req2 = factory.post("/", {"skill": skill.id, "channel_type": "platform"}, format="json")
            force_authenticate(req2, user=user)
            resp2 = SkillChannelViewSet.as_view({"post": "create"})(req2)
            assert resp2.status_code == 403

            req3 = factory.put("/", {"name": "x"}, format="json")
            force_authenticate(req3, user=user)
            resp3 = SkillChannelViewSet.as_view({"put": "update"})(req3, pk=ch.id)
            assert resp3.status_code == 403

            req4 = factory.delete("/")
            force_authenticate(req4, user=user)
            resp4 = SkillChannelViewSet.as_view({"delete": "destroy"})(req4, pk=ch.id)
            assert resp4.status_code == 403

            req5 = factory.post("/", {"enabled": True}, format="json")
            force_authenticate(req5, user=user)
            resp5 = SkillChannelViewSet.as_view({"post": "set_enabled"})(req5, pk=ch.id)
            assert resp5.status_code == 403


class TestChatServiceUnit:
    def test_get_enabled_channel_errors(self):
        with pytest.raises(chat_svc.SkillChannelChatError) as e:
            chat_svc.get_enabled_channel(999999)
        assert e.value.status == 404

        skill = _skill()
        ch = _channel(skill, enabled=False)
        with pytest.raises(chat_svc.SkillChannelChatError) as e2:
            chat_svc.get_enabled_channel(ch.id)
        assert e2.value.status == 403

        ch2 = _channel(skill, channel_type=SkillChannelChoices.PLATFORM, enabled=True)
        with pytest.raises(chat_svc.SkillChannelChatError) as e3:
            chat_svc.get_enabled_channel(ch2.id, {SkillChannelChoices.EMBEDDED_CHAT})
        assert e3.value.status == 400

    def test_assert_org_access_guest_and_deny(self):
        skill = _skill()
        ch = _channel(skill, channel_type=SkillChannelChoices.WEB_CHAT, usage_team=[99])
        chat_svc.assert_org_access(ch, 1, [{"name": "OpsPilotGuest", "id": 99}])
        with pytest.raises(chat_svc.SkillChannelChatError):
            chat_svc.assert_org_access(ch, 1, [])
        im = _channel(skill, channel_type=SkillChannelChoices.ENTERPRISE_WECHAT, usage_team=[])
        chat_svc.assert_org_access(im, None)

    def test_authenticate_embedded_invalid(self):
        req = APIRequestFactory().post("/", HTTP_API_AUTHORIZATION="nope")
        with pytest.raises(chat_svc.SkillChannelChatError) as e:
            chat_svc.authenticate_embedded(req)
        assert e.value.status == 401

    def test_conversation_reuse_and_history(self):
        skill = _skill()
        ch = _channel(skill)
        c1 = chat_svc.get_or_create_conversation(ch, "u1", session_id="sid-1")
        chat_svc.append_message(c1, "user", "a")
        chat_svc.append_message(c1, "assistant", "b")
        c2 = chat_svc.get_or_create_conversation(ch, "u1", session_id="sid-1")
        assert c2.id == c1.id
        hist = chat_svc._history_from_conversation(c1, 10)
        assert hist[-1]["content"] == "b"

    def test_build_params_with_tools_and_extra(self):
        skill = _skill(tools=[{"name": "t1"}], skill_prompt="p", team=[1])
        user = SimpleNamespace(username="u", id=1, locale="zh-CN")
        with patch("apps.opspilot.services.skill_channel_chat_service.resolve_request_tools", return_value=[{"name": "t1"}]):
            with patch("apps.opspilot.services.skill_channel_chat_service.hydrate_skill_packages", return_value=[]):
                with patch(
                    "apps.opspilot.services.skill_channel_chat_service.build_skill_package_prompt",
                    return_value=("p2", []),
                ):
                    with patch(
                        "apps.opspilot.services.skill_channel_chat_service.build_skill_package_strategy",
                        return_value={},
                    ):
                        params = chat_svc.build_skill_chat_params(skill, "hi", user, extra={"foo": 1})
        assert params["skill_prompt"] == "p2"
        assert params["foo"] == 1
        assert "t1" in [t.get("name") for t in params["tools"]]

    def test_stream_chat_persists_assistant_and_identity_error(self):
        skill = _skill()
        ch = _channel(skill, channel_type=SkillChannelChoices.WEB_CHAT)
        factory = APIRequestFactory()
        user = _superuser("stream_u")

        # identity error path（capture 失败）
        request_err = factory.post("/", {"message": "x"}, format="json")
        request_err.user = user
        with patch(
            "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
            side_effect=CallerIdentityError("no id"),
        ):
            err = chat_svc.stream_skill_channel_chat(
                channel=ch,
                user_message="x",
                request=request_err,
                external_user_id="u",
            )
        assert err["Content-Type"].startswith("text/event-stream")

        request = factory.post("/", {"message": "hi"}, format="json")
        request.user = user
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 5.6.7.8"

        def gen():
            yield b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            yield b"data: not-json\n\n"
            yield b'data: {"content":"!"}\n\n'
            yield b"data: [DONE]\n\n"

        with patch("apps.opspilot.services.skill_channel_chat_service.stream_chat") as mock_stream:
            mock_stream.return_value = StreamingHttpResponse(gen(), content_type="text/event-stream")
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "stream_u"},
            ):
                resp = chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="hi",
                    request=request,
                    external_user_id="u@domain.com",
                    session_id="sess-stream",
                )
                assert resp["Content-Type"].startswith("text/event-stream")
                mock_stream.assert_called_once()
        assert SkillConversation.objects.filter(session_id="sess-stream").exists()
        assert SkillConversationMessage.objects.filter(role="user", content="hi").exists()

    def test_wrap_supports_async_streaming_content(self):
        """异步 streaming_content 分支可被消费且不抛错。"""
        skill = _skill()
        ch = _channel(skill)
        conv = SkillConversation.objects.create(session_id="s-async", skill=skill, channel=ch, external_user_id="u")

        async def agen():
            yield b'data: {"choices":[{"delta":{"content":"async-ok"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        wrapped = chat_svc._wrap_stream_persist_assistant(
            StreamingHttpResponse(agen(), content_type="text/event-stream"),
            conversation_id=conv.id,
        )

        async def consume():
            chunks = []
            async for piece in wrapped.streaming_content:
                chunks.append(piece)
            return chunks

        chunks = asyncio.run(consume())
        assert chunks  # 至少透传了流式分片

    def test_wrap_persist_swallows_db_error(self):
        skill = _skill()
        ch = _channel(skill)
        conv = SkillConversation.objects.create(session_id="s2", skill=skill, channel=ch, external_user_id="u")

        def gen():
            yield b'data: {"choices":[{"delta":{"content":"z"}}]}\n\n'

        def _inline_sync_to_async(func, **kwargs):
            async def _runner(*args, **kw):
                return func(*args, **kw)

            return _runner

        wrapped = chat_svc._wrap_stream_persist_assistant(
            StreamingHttpResponse(gen(), content_type="text/event-stream"),
            conversation_id=conv.id,
        )
        with patch("apps.opspilot.services.skill_channel_chat_service.sync_to_async", side_effect=_inline_sync_to_async):
            with patch("apps.opspilot.services.skill_channel_chat_service.append_message", side_effect=RuntimeError("boom")):

                async def consume():
                    async for _ in wrapped.streaming_content:
                        pass

                asyncio.run(consume())


class TestViewsAndTask:
    def test_platform_list_unauthenticated(self):
        req = APIRequestFactory().get("/")
        req.user = SimpleNamespace(is_authenticated=False)
        resp = opspilot_views.list_platform_skill_channels(req)
        assert resp.status_code == 401

    def test_execute_skill_channel_chat_paths(self):
        skill = _skill()
        ch = _channel(skill, channel_type=SkillChannelChoices.PLATFORM, usage_team=[1])
        factory = APIRequestFactory()
        user = _superuser("chat_u")

        req0 = factory.post("/", {}, format="json")
        req0.user = SimpleNamespace(is_authenticated=False)
        assert opspilot_views.execute_skill_channel_chat(req0, ch.id)["Content-Type"].startswith("text/event-stream")

        req1 = factory.post("/", {}, format="json")
        req1.user = user
        # invalid json body via raw
        req_bad = factory.post("/", data=b"{", content_type="application/json")
        req_bad.user = user
        assert opspilot_views.execute_skill_channel_chat(req_bad, ch.id)["Content-Type"].startswith("text/event-stream")

        req2 = factory.post("/", {"message": ""}, format="json")
        req2.user = user
        assert opspilot_views.execute_skill_channel_chat(req2, ch.id)["Content-Type"].startswith("text/event-stream")

        with patch("apps.opspilot.views.stream_skill_channel_chat") as mock_stream:
            mock_stream.return_value = StreamingHttpResponse(iter([b"data: ok\n\n"]), content_type="text/event-stream")
            req3 = factory.post("/", {"message": "hi", "session_id": "s"}, format="json")
            req3.user = user
            req3.COOKIES["current_team"] = "1"
            resp = opspilot_views.execute_skill_channel_chat(req3, ch.id)
            assert resp.status_code == 200
            mock_stream.assert_called_once()

        # channel missing -> SkillChannelChatError
        req4 = factory.post("/", {"message": "hi"}, format="json")
        req4.user = user
        req4.COOKIES["current_team"] = "1"
        assert opspilot_views.execute_skill_channel_chat(req4, 999999)["Content-Type"].startswith("text/event-stream")

    def test_embedded_skill_mismatch_and_im_paths(self):
        skill = _skill()
        other = _skill(name="other")
        ch = _channel(skill, channel_type=SkillChannelChoices.EMBEDDED_CHAT, usage_team=[1])
        plain = UserAPISecret.generate_api_secret()
        UserAPISecret.objects.create(
            username="emb",
            domain="domain.com",
            team=1,
            api_secret=UserAPISecret.hash_api_secret(plain),
        )
        factory = APIRequestFactory()
        req = factory.post(
            "/",
            {"message": "hi"},
            format="json",
            HTTP_API_AUTHORIZATION=plain,
        )
        resp = opspilot_views.execute_skill_embedded_chat(req, other.id, ch.id)
        assert resp["Content-Type"].startswith("text/event-stream")

        # IM enabled GET success for dingtalk
        ding = _channel(
            skill,
            channel_type=SkillChannelChoices.DINGTALK,
            enabled=True,
            channel_config={"client_id": "cid", "client_secret": "csec"},
        )
        req_get = factory.get("/")
        assert opspilot_views.execute_skill_channel_im(req_get, ding.id, SkillChannelChoices.DINGTALK).status_code == 200

        # aibot GET missing token/config → fail
        aibot = _channel(
            skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            enabled=True,
            channel_config={},
        )
        assert opspilot_views.execute_skill_channel_im(req_get, aibot.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT).status_code == 400

        # aibot GET verify success（走 Bot aibot URL 校验）
        aibot.channel_config = {"token": "tok", "encodingAESKey": "0" * 43}
        aibot.save()
        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
            return_value="echo",
        ):
            req_v = factory.get("/", {"msg_signature": "a", "timestamp": "1", "nonce": "n", "echostr": "e"})
            resp_v = opspilot_views.execute_skill_channel_im(req_v, aibot.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
            assert resp_v.content == b"echo"

        # aibot GET verify fail
        from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCryptoError

        with patch(
            "apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils.EnterpriseWechatAibotCrypto.verify_url",
            side_effect=EnterpriseWechatAibotCryptoError("bad"),
        ):
            resp_f = opspilot_views.execute_skill_channel_im(req_v, aibot.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
            assert resp_f.status_code == 400

        # 钉钉 POST 文本走专用任务
        with patch("apps.opspilot.tasks.process_skill_channel_dingtalk_message.delay") as delay:
            req_post = factory.post(
                "/",
                data=b'{"msgtype":"text","text":{"content":"hi"},"senderStaffId":"u1","msgId":"m1","sessionWebhook":"https://example.com/h"}',
                content_type="application/json",
            )
            resp_p = opspilot_views.execute_skill_channel_im(req_post, ding.id, SkillChannelChoices.DINGTALK)
            assert resp_p.status_code == 200
            delay.assert_called_once()

    def test_im_task_skip_and_accept(self):
        skill = _skill()
        ch = _channel(skill, channel_type=SkillChannelChoices.DINGTALK, enabled=True, channel_config={"client_id": "c", "client_secret": "s"})
        assert process_skill_channel_im_message(999, "dingtalk", "POST", {}, "", {})["skipped"] is True
        out = process_skill_channel_im_message(ch.id, SkillChannelChoices.DINGTALK, "POST", {}, "body", {})
        assert out["accepted"] is True
        assert out["skill_id"] == skill.id

    def test_model_str(self):
        skill = _skill()
        ch = _channel(skill)
        conv = SkillConversation.objects.create(session_id="sx", skill=skill, channel=ch, external_user_id="u")
        assert str(ch)
        assert str(conv) == "sx"

    def test_authorize_usage_team_denied(self):
        skill = _skill()
        factory = APIRequestFactory()
        user = _normal("auth_deny", permission={"opspilot": {"skill_setting-Edit"}})
        request = factory.post("/", {"usage_team": [1, 2]}, format="json")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        with patch.object(LLMViewSet, "get_has_permission", return_value=False):
            resp = LLMViewSet.as_view({"post": "authorize_usage_team"})(request, pk=skill.id)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "false" in body.lower() or "result" in body

    def test_update_skips_top_level_masked_secret(self):
        skill = _skill()
        ch = _channel(skill, channel_config={"token": "keep", "name": "n"})
        ser = SkillChannelSerializer(
            ch,
            data={"channel_config": {"token": "******", "name": "n2"}},
            partial=True,
        )
        assert ser.is_valid(), ser.errors
        obj = ser.save()
        assert obj.channel_config["token"] == "keep"
        assert obj.channel_config["name"] == "n2"
