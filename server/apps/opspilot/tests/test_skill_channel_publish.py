"""智能体 usage_team 与渠道发布核心行为测试。"""

import json
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User, UserAPISecret
from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.skill_channel_service import sync_skill_channel_usage_teams
from apps.opspilot.services.usage_team import merge_usage_team
from apps.opspilot.viewsets.llm_view import LLMViewSet
from apps.opspilot.viewsets.skill_channel_view import SkillChannelViewSet

pytestmark = pytest.mark.django_db


def _superuser(username="skill_pub_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}, {"id": 2, "name": "T2"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _skill(**kwargs):
    defaults = {"name": "s1", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


class TestMergeUsageTeam:
    def test_forces_management_org_first(self):
        assert merge_usage_team([1], [2, 1, 3]) == [1, 2, 3]

    def test_empty_usage_keeps_team(self):
        assert merge_usage_team([1, 2], []) == [1, 2]


class TestSkillUsageTeamViews:
    def test_create_merges_usage_team(self):
        factory = APIRequestFactory()
        user = _superuser()
        request = factory.post("/", {"name": "n1", "team": [1], "usage_team": [2]}, format="json")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"post": "create"})(request)
        assert resp.status_code == 201
        skill = LLMSkill.objects.get(name="n1")
        assert skill.usage_team == [1, 2]

    def test_update_syncs_channel_usage_team(self):
        skill = _skill(usage_team=[1])
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
        )
        factory = APIRequestFactory()
        user = _superuser("su2")
        request = factory.put(
            "/",
            {"name": skill.name, "team": [1], "usage_team": [1, 2]},
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"put": "update"})(request, pk=skill.id)
        assert resp.status_code == 200
        ch.refresh_from_db()
        assert ch.usage_team == [1, 2]

    def test_authorize_usage_team_syncs_channels(self):
        skill = _skill()
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=False,
            usage_team=[1],
        )
        factory = APIRequestFactory()
        user = _superuser("su3")
        request = factory.post("/", {"usage_team": [1, 2]}, format="json")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"post": "authorize_usage_team"})(request, pk=skill.id)
        assert resp.status_code == 200
        ch.refresh_from_db()
        assert ch.usage_team == [1, 2]


class TestSkillChannelCrud:
    def test_create_copies_usage_team(self):
        skill = _skill(usage_team=[1, 2])
        factory = APIRequestFactory()
        user = _superuser("su4")
        request = factory.post(
            "/",
            {"skill": skill.id, "channel_type": SkillChannelChoices.PLATFORM, "enabled": True},
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = SkillChannelViewSet.as_view({"post": "create"})(request)
        assert resp.status_code == 201
        ch = SkillChannel.objects.get(skill=skill, channel_type=SkillChannelChoices.PLATFORM)
        assert ch.usage_team == [1, 2]
        assert ch.enabled is True

    def test_rejects_duplicate_name_same_skill_and_channel_type(self):
        skill = _skill(usage_team=[1])
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
            name="同名渠道",
        )
        factory = APIRequestFactory()
        user = _superuser("su_dup")
        request = factory.post(
            "/",
            {
                "skill": skill.id,
                "channel_type": SkillChannelChoices.PLATFORM,
                "name": "同名渠道",
                "enabled": False,
            },
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = SkillChannelViewSet.as_view({"post": "create"})(request)
        assert resp.status_code == 400
        assert SkillChannel.objects.filter(skill=skill, channel_type=SkillChannelChoices.PLATFORM).count() == 1

        # 不同类型允许同名
        request2 = factory.post(
            "/",
            {
                "skill": skill.id,
                "channel_type": SkillChannelChoices.WEB_CHAT,
                "name": "同名渠道",
                "enabled": False,
            },
            format="json",
        )
        force_authenticate(request2, user=user)
        request2.COOKIES["current_team"] = "1"
        resp2 = SkillChannelViewSet.as_view({"post": "create"})(request2)
        assert resp2.status_code == 201

    def test_set_enabled_and_im_reject_when_offline(self):
        skill = _skill()
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
            enabled=True,
            usage_team=[1],
            channel_config={"token": "t", "encodingAESKey": "x" * 43},
        )
        factory = APIRequestFactory()
        user = _superuser("su5")
        request = factory.post("/", {"enabled": False}, format="json")
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = SkillChannelViewSet.as_view({"post": "set_enabled"})(request, pk=ch.id)
        assert resp.status_code == 200
        ch.refresh_from_db()
        assert ch.enabled is False

        req2 = factory.get(f"/skill_channel/{ch.id}/enterprise_wechat_aibot/")
        resp2 = opspilot_views.execute_skill_channel_im(req2, ch.id, SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT)
        assert resp2.status_code == 403

    def test_delete_skill_cascades_channels_and_conversations(self):
        skill = _skill()
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
        )
        conv = SkillConversation.objects.create(
            session_id="sess-1",
            skill=skill,
            channel=ch,
            external_user_id="u1",
        )
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="hi")
        skill_id = skill.id
        skill.delete()
        assert not SkillChannel.objects.filter(skill_id=skill_id).exists()
        assert not SkillConversation.objects.filter(session_id="sess-1").exists()
        assert not SkillConversationMessage.objects.filter(content="hi").exists()


class TestPlatformListAndEmbeddedGate:
    def test_platform_list_filters_by_usage_team(self):
        skill = _skill(usage_team=[1])
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
            name="p1",
        )
        other = _skill(name="s2", team=[2], usage_team=[2])
        SkillChannel.objects.create(
            skill=other,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[2],
            name="p2",
        )
        factory = APIRequestFactory()
        user = _superuser("su6")
        request = factory.get("/skill_channel/platform/")
        request.user = user
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.list_platform_skill_channels(request)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "p1" in body
        assert "p2" not in body

    def test_web_chat_list_filters_by_usage_team(self):
        skill = _skill(usage_team=[1], enable_conversation_history=True)
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[1],
            name="w1",
            channel_config={"appName": "WebApp1"},
        )
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
            name="platform-should-not-list",
        )
        other = _skill(name="s2", team=[2], usage_team=[2])
        SkillChannel.objects.create(
            skill=other,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[2],
            name="w2",
        )
        factory = APIRequestFactory()
        user = _superuser("su_web")
        request = factory.get("/skill_channel/web_chat/")
        request.user = user
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.list_web_chat_skill_channels(request)
        assert resp.status_code == 200
        body = json.loads(resp.content.decode())
        names = [row["name"] for row in body["data"]]
        assert "w1" in names
        assert "w2" not in names
        assert "platform-should-not-list" not in names
        w1 = next(row for row in body["data"] if row["name"] == "w1")
        assert w1["enable_conversation_history"] is True

    def test_embedded_requires_api_secret(self):
        skill = _skill(usage_team=[1])
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.EMBEDDED_CHAT,
            enabled=True,
            usage_team=[1],
        )
        factory = APIRequestFactory()
        request = factory.post(
            f"/skill_channel/embedded/{skill.id}/{ch.id}/",
            {"message": "hi"},
            format="json",
        )
        resp = opspilot_views.execute_skill_embedded_chat(request, skill.id, ch.id)
        assert resp.status_code == 200
        # StreamingHttpResponse may use async generator; consume via streaming_content if sync
        chunks = []
        try:
            for piece in resp.streaming_content:
                chunks.append(piece if isinstance(piece, (bytes, bytearray)) else str(piece).encode())
        except TypeError:
            # async streaming: just assert response type
            assert resp["Content-Type"].startswith("text/event-stream")
            return
        content = b"".join(chunks).decode()
        assert "Api-Authorization" in content or "缺少" in content

    def test_embedded_accepts_valid_secret_team(self):
        skill = _skill(usage_team=[1])
        ch = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.EMBEDDED_CHAT,
            enabled=True,
            usage_team=[1],
        )
        plain = UserAPISecret.generate_api_secret()
        UserAPISecret.objects.create(
            username="apiuser",
            domain="domain.com",
            team=1,
            api_secret=UserAPISecret.hash_api_secret(plain),
        )
        factory = APIRequestFactory()
        request = factory.post(
            f"/skill_channel/embedded/{skill.id}/{ch.id}/",
            {"message": "hi"},
            format="json",
            HTTP_API_AUTHORIZATION=plain,
        )
        with patch("apps.opspilot.services.skill_channel_chat_service.stream_agui_chat") as mock_stream:
            from django.http import StreamingHttpResponse

            def gen():
                yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
                yield b"data: [DONE]\n\n"

            mock_stream.return_value = StreamingHttpResponse(gen(), content_type="text/event-stream")
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "apiuser", "domain": "domain.com", "group": 1},
            ):
                resp = opspilot_views.execute_skill_embedded_chat(request, skill.id, ch.id)
            assert resp.status_code == 200
            mock_stream.assert_called_once()
        assert SkillConversation.objects.filter(channel=ch).exists()
        assert SkillConversationMessage.objects.filter(role="user", content="hi").exists()


class TestSkillConversationHistory:
    def _web_channel(self, skill, **kwargs):
        defaults = dict(channel_type=SkillChannelChoices.WEB_CHAT, enabled=True, usage_team=[1], name="web")
        defaults.update(kwargs)
        return SkillChannel.objects.create(skill=skill, **defaults)

    def test_lists_current_user_sessions_with_channel_type(self):
        skill = _skill()
        web = self._web_channel(skill)
        platform = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
            name="platform",
        )
        wechat = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT,
            enabled=True,
            usage_team=[1],
            name="wechat",
        )
        user = _superuser("hist_su")
        uid = f"{user.username}@{user.domain}"
        SkillConversation.objects.create(session_id="web-1", skill=skill, channel=web, external_user_id=uid, title="网页问")
        SkillConversation.objects.create(session_id="plat-1", skill=skill, channel=platform, external_user_id=uid, title="平台问")
        SkillConversation.objects.create(session_id="wx-other", skill=skill, channel=wechat, external_user_id="wx-openid")
        factory = APIRequestFactory()
        request = factory.get("/skill_channel/conversations/", {"channel_id": web.id})
        request.user = user
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.list_skill_channel_conversations(request)
        assert resp.status_code == 200
        body = json.loads(resp.content)
        sessions = {row["session_id"]: row for row in body["data"]}
        assert sessions["web-1"]["channel_type"] == SkillChannelChoices.WEB_CHAT
        assert sessions["plat-1"]["channel_type"] == SkillChannelChoices.PLATFORM
        assert "wx-other" not in sessions

    def test_messages_and_delete_are_owner_scoped(self):
        skill = _skill()
        web = self._web_channel(skill)
        owner = _superuser("hist_owner")
        other = _superuser("hist_other")
        uid = f"{owner.username}@{owner.domain}"
        conv = SkillConversation.objects.create(session_id="own-1", skill=skill, channel=web, external_user_id=uid)
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="你好智能体")
        SkillConversationMessage.objects.create(conversation=conv, role="assistant", content="收到")
        factory = APIRequestFactory()

        owner_msg = factory.get("/skill_channel/conversations/messages/", {"session_id": "own-1"})
        owner_msg.user = owner
        owner_resp = opspilot_views.list_skill_channel_session_messages(owner_msg)
        owner_body = json.loads(owner_resp.content)
        assert owner_resp.status_code == 200
        assert [row["conversation_content"] for row in owner_body["data"]["messages"]] == ["你好智能体", "收到"]
        assert owner_body["data"]["llm_context_usage"] is None

        other_msg = factory.get("/skill_channel/conversations/messages/", {"session_id": "own-1"})
        other_msg.user = other
        other_resp = opspilot_views.list_skill_channel_session_messages(other_msg)
        assert other_resp.status_code == 403

        other_del = factory.post("/skill_channel/conversations/delete/", {"session_id": "own-1"}, format="json")
        other_del.user = other
        assert opspilot_views.delete_skill_channel_session(other_del).status_code == 403
        assert SkillConversation.objects.filter(session_id="own-1").exists()

        owner_del = factory.post("/skill_channel/conversations/delete/", {"session_id": "own-1"}, format="json")
        owner_del.user = owner
        del_resp = opspilot_views.delete_skill_channel_session(owner_del)
        assert del_resp.status_code == 200
        assert not SkillConversation.objects.filter(session_id="own-1").exists()
        assert not SkillConversationMessage.objects.filter(conversation_id=conv.id).exists()

    def test_messages_include_usage_snapshot_when_history_enabled(self):
        secret = "sk-session-usage-PROMPT-SENTINEL"
        skill = _skill(enable_conversation_history=True, skill_prompt="你是排障助手。")
        web = self._web_channel(skill)
        owner = _superuser("hist_usage")
        uid = f"{owner.username}@{owner.domain}"
        conv = SkillConversation.objects.create(session_id="usage-1", skill=skill, channel=web, external_user_id=uid)
        SkillConversationMessage.objects.create(conversation=conv, role="user", content=f"磁盘空间 {secret}")
        SkillConversationMessage.objects.create(conversation=conv, role="assistant", content="需要看使用率趋势")
        factory = APIRequestFactory()
        request = factory.get("/skill_channel/conversations/messages/", {"session_id": "usage-1"})
        request.user = owner
        resp = opspilot_views.list_skill_channel_session_messages(request)
        body = json.loads(resp.content)
        assert resp.status_code == 200
        usage = body["data"]["llm_context_usage"]
        assert usage is not None
        assert usage["packet_tokens"] > 0
        assert usage["input_working_tokens"] > 0
        assert usage["window_tokens"] > 0
        rendered = json.dumps(usage, ensure_ascii=False)
        assert secret not in rendered
        assert "磁盘空间" not in rendered
        assert [row["conversation_content"] for row in body["data"]["messages"]][0].endswith(secret)

    def test_first_user_message_sets_title_and_reuse_across_channels(self):
        from apps.opspilot.services.skill_channel_chat_service import append_message, get_or_create_conversation

        skill = _skill()
        web = self._web_channel(skill)
        platform = SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.PLATFORM,
            enabled=True,
            usage_team=[1],
        )
        conv = get_or_create_conversation(web, "u@domain.com", session_id="shared-1")
        long_msg = "标题" + ("字" * 60)
        append_message(conv, "user", long_msg)
        conv.refresh_from_db()
        assert conv.title == f"{long_msg[:50]}..."
        reused = get_or_create_conversation(platform, "u@domain.com", session_id="shared-1")
        assert reused.id == conv.id


class TestPublishedWebSkillApis:
    def test_lists_unique_web_skills_for_current_team(self):
        skill = _skill(name="web-skill", usage_team=[1])
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[1],
            name="w-a",
        )
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[1],
            name="w-b",
        )
        other = _skill(name="other-skill", team=[2], usage_team=[2])
        SkillChannel.objects.create(
            skill=other,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[2],
        )
        factory = APIRequestFactory()
        user = _superuser("web_skill_su")
        request = factory.get("/skill_channel/web_skills/")
        request.user = user
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.list_published_web_skills(request)
        assert resp.status_code == 200
        data = json.loads(resp.content)["data"]
        ids = [row["id"] for row in data]
        assert ids.count(skill.id) == 1
        assert other.id not in ids
        published = next(row for row in data if row["id"] == skill.id)
        assert published["enable_conversation_history"] is False

    def test_agui_chat_loads_skill_and_truncates_history(self):
        skill = _skill(name="agui-skill", usage_team=[1], conversation_window_size=2)
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[1],
        )
        factory = APIRequestFactory()
        user = _superuser("agui_su")
        history = [{"event": "user", "message": f"m{i}"} for i in range(5)]
        request = factory.post(
            f"/skill_channel/skill/{skill.id}/chat/",
            {
                "user_message": "最新问题",
                "chat_history": history,
                "conversation_window_size": 99,
                "llm_model": 999,
                "tools": [{"name": "should_ignore"}],
            },
            format="json",
        )
        request.user = user
        request.COOKIES["current_team"] = "1"
        with patch("apps.opspilot.views.stream_agui_chat") as mock_stream:
            from django.http import StreamingHttpResponse

            mock_stream.return_value = StreamingHttpResponse(iter([b"data: ok\n\n"]), content_type="text/event-stream")
            with patch(
                "apps.opspilot.views.capture_caller_identity",
                return_value={"username": user.username, "domain": user.domain, "group": 1},
            ):
                resp = opspilot_views.execute_published_web_skill_chat(request, skill.id)
            assert resp.status_code == 200
            mock_stream.assert_called_once()
            params = mock_stream.call_args.args[0]
        assert params["conversation_window_size"] == 2
        assert [item["message"] for item in params["chat_history"]] == ["m3", "m4"]
        assert params["user_message"] == "最新问题"
        assert params["skill_id"] == skill.id
        assert params.get("llm_model") != 999
        assert params.get("tools") != [{"name": "should_ignore"}]

    def test_agui_chat_rejects_unpublished_or_other_team(self):
        skill = _skill(usage_team=[2])
        SkillChannel.objects.create(
            skill=skill,
            channel_type=SkillChannelChoices.WEB_CHAT,
            enabled=True,
            usage_team=[2],
        )
        factory = APIRequestFactory()
        user = _superuser("agui_denied")
        request = factory.post(
            f"/skill_channel/skill/{skill.id}/chat/",
            {"user_message": "hi", "chat_history": []},
            format="json",
        )
        request.user = user
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.execute_published_web_skill_chat(request, skill.id)
        chunks = []
        try:
            for piece in resp.streaming_content:
                chunks.append(piece if isinstance(piece, (bytes, bytearray)) else str(piece).encode())
        except TypeError:
            assert resp["Content-Type"].startswith("text/event-stream")
            return
        content = b"".join(chunks).decode()
        assert "无权" in content or "未发布" in content

    def test_skill_approval_and_choice_allow_local_agui_nodes(self):
        from types import SimpleNamespace

        factory = APIRequestFactory()
        user = SimpleNamespace(username="alice", domain="d", team=1, locale="en")
        qs_mock = MagicMock()
        qs_mock.order_by.return_value.first.return_value = None
        qs_mock.exists.return_value = False
        with (
            patch.object(opspilot_views, "validate_openai_token", return_value=(True, user)),
            patch.object(opspilot_views, "extract_api_token", return_value="tok"),
            patch.object(opspilot_views.WorkFlowTaskResult.objects, "filter", return_value=qs_mock),
            patch("apps.opspilot.services.approval.submit_approval_decision") as submit_approval,
            patch("apps.opspilot.utils.user_choice.submit_user_choice") as submit_choice,
            patch.object(opspilot_views, "request_interrupt") as interrupt,
        ):
            approval_req = factory.post(
                "/bot_mgmt/submit_approval/",
                {"execution_id": "exec-skill", "node_id": "skill_test", "tool_call_id": "t1", "decision": "approve"},
                format="json",
            )
            approval_resp = opspilot_views.submit_approval(approval_req)
            assert approval_resp.status_code == 200
            submit_approval.assert_called_once()

            choice_req = factory.post(
                "/bot_mgmt/submit_choice/",
                {"execution_id": "exec-skill", "node_id": "skill_test", "choice_id": "c1", "selected": ["opt1"]},
                format="json",
            )
            choice_resp = opspilot_views.submit_choice(choice_req)
            assert choice_resp.status_code == 200
            submit_choice.assert_called_once()

            interrupt_req = factory.post(
                "/bot_mgmt/interrupt_chat_flow_execution/",
                {"execution_id": "exec-skill", "reason": "user_manual"},
                format="json",
            )
            interrupt_resp = opspilot_views.interrupt_chat_flow_execution(interrupt_req)
            assert interrupt_resp.status_code == 200
            interrupt.assert_called_once()


class TestSyncHelper:
    def test_sync_updates_all_channels(self):
        skill = _skill(usage_team=[1, 9])
        a = SkillChannel.objects.create(skill=skill, channel_type="platform", usage_team=[1])
        b = SkillChannel.objects.create(skill=skill, channel_type="web_chat", usage_team=[1])
        n = sync_skill_channel_usage_teams(skill)
        assert n == 2
        a.refresh_from_db()
        b.refresh_from_db()
        assert a.usage_team == [1, 9]
        assert b.usage_team == [1, 9]
