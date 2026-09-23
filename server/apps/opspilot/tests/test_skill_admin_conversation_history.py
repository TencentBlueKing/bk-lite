"""智能体详情管理侧会话历史：只读列表/消息与权限边界。"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.skill_channel_chat_service import append_message, delete_skill_session, saas_external_user_id
from apps.opspilot.viewsets.skill_channel_view import SkillChannelViewSet
from apps.system_mgmt.models import User as SystemUser

pytestmark = pytest.mark.django_db

ALICE_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
LIST_LOG_TEMPLATE = (
    "event=skill_admin_conversations_listed skill_id=%s channel_id=%s has_person=%s " "has_title=%s has_time=%s page=%s page_size=%s count=%s"
)
MESSAGE_LOG_TEMPLATE = "event=skill_admin_conversation_messages_read skill_id=%s channel_id=%s session_id=%s"


def _superuser(username="hist_admin"):
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


def _normal(username="hist_user", groups=None, permission=None):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=groups or [{"id": 2, "name": "T2"}],
        roles=["normal"],
    )
    user.is_superuser = False
    user.save()
    user.permission = permission or {
        "opspilot": {"skill_setting-View", "skill_setting-Edit"},
    }
    return user


def _skill(**kwargs):
    defaults = {"name": "hist-skill", "team": [1], "usage_team": [1]}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _channel(skill, **kwargs):
    defaults = {
        "skill": skill,
        "channel_type": SkillChannelChoices.WEB_CHAT,
        "enabled": True,
        "usage_team": list(skill.usage_team or [1]),
        "name": "web",
        "channel_config": {},
    }
    defaults.update(kwargs)
    return SkillChannel.objects.create(**defaults)


def _conv(skill, channel, *, session_id, external_user_id, title=""):
    return SkillConversation.objects.create(
        session_id=session_id,
        skill=skill,
        channel=channel,
        external_user_id=external_user_id,
        title=title,
    )


def _body(resp):
    if hasattr(resp, "data") and resp.data is not None and not isinstance(resp, type(None)):
        data = resp.data
        if isinstance(data, (dict, list)):
            return data
    return json.loads(resp.content)


def _list(request_user, **params):
    factory = APIRequestFactory()
    current_team = str(params.pop("current_team", "1"))
    request = factory.get("/opspilot/model_provider_mgmt/skill_channel/admin_conversations/", params)
    force_authenticate(request, user=request_user)
    request.COOKIES["current_team"] = current_team
    return SkillChannelViewSet.as_view({"get": "admin_conversations"})(request)


def _messages(request_user, session_id, current_team="1"):
    factory = APIRequestFactory()
    request = factory.get(
        "/opspilot/model_provider_mgmt/skill_channel/admin_conversation_messages/",
        {"session_id": session_id},
    )
    force_authenticate(request, user=request_user)
    request.COOKIES["current_team"] = current_team
    return SkillChannelViewSet.as_view({"get": "admin_conversation_messages"})(request)


class TestSkillAdminConversationHistory:
    def test_manager_lists_all_channels_and_people(self):
        skill = _skill(usage_team=[1, 2])
        web = _channel(skill, name="网页入口")
        wecom = _channel(
            skill,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT,
            name="生产企微",
        )
        _conv(skill, web, session_id="s-web", external_user_id="alice@domain.com", title="网页问")
        _conv(skill, wecom, session_id="s-wx", external_user_id="wx-openid", title="企微问")
        admin = _superuser()
        resp = _list(admin, skill_id=skill.id)
        assert resp.status_code == 200
        payload = _body(resp)
        assert payload["result"] is True
        items = {row["session_id"]: row for row in payload["data"]["items"]}
        assert payload["data"]["count"] == 2
        assert items["s-web"]["channel_name"] == "网页入口"
        assert items["s-web"]["channel_type"] == SkillChannelChoices.WEB_CHAT
        assert items["s-wx"]["external_user_id"] == "wx-openid"
        assert items["s-wx"]["person_display"] == "wx-openid"

    def test_usage_org_member_cannot_list_or_read(self):
        skill = _skill(team=[1], usage_team=[1, 2])
        web = _channel(skill)
        _conv(skill, web, session_id="s-1", external_user_id="alice@domain.com", title="问")
        user = _normal()
        list_resp = _list(user, skill_id=skill.id, current_team="2")
        assert list_resp.status_code == 403
        msg_resp = _messages(user, "s-1", current_team="2")
        assert msg_resp.status_code == 403

    def test_other_skill_manager_cannot_list(self):
        mine = _skill(name="mine", team=[1], usage_team=[1])
        other = _skill(name="other", team=[2], usage_team=[2])
        web = _channel(other)
        _conv(other, web, session_id="other-1", external_user_id="u", title="别人的")
        admin = _superuser()
        # 超管可看任意；用普通管理组用户锁跨智能体
        manager = _normal(
            "mgr1",
            groups=[{"id": 1, "name": "T1"}],
            permission={"opspilot": {"skill_setting-View"}},
        )
        resp = _list(manager, skill_id=other.id, current_team="1")
        assert resp.status_code == 403
        own = _list(admin, skill_id=mine.id)
        assert own.status_code == 200

    def test_filters_by_channel_binding_not_type(self):
        skill = _skill()
        prod = _channel(skill, channel_type=SkillChannelChoices.ENTERPRISE_WECHAT, name="生产企微")
        test = _channel(skill, channel_type=SkillChannelChoices.ENTERPRISE_WECHAT, name="测试企微")
        _conv(skill, prod, session_id="prod-1", external_user_id="u1", title="生产")
        _conv(skill, test, session_id="test-1", external_user_id="u2", title="测试")
        admin = _superuser()
        resp = _list(admin, skill_id=skill.id, channel_id=prod.id)
        items = _body(resp)["data"]["items"]
        assert [row["session_id"] for row in items] == ["prod-1"]

    def test_person_filter_matches_display_name_and_raw_id(self):
        skill = _skill()
        web = _channel(skill)
        SystemUser.objects.create(
            username="alice",
            domain="domain.com",
            display_name="爱丽丝",
            email="alice@domain.com",
            password="x",
            user_id=ALICE_UUID,
        )
        _conv(skill, web, session_id="uuid-1", external_user_id=ALICE_UUID, title="平台问")
        _conv(skill, web, session_id="wx-1", external_user_id="wecom-zhang", title="企微问")
        admin = _superuser()
        by_name = _list(admin, skill_id=skill.id, person="爱丽丝")
        assert [row["session_id"] for row in _body(by_name)["data"]["items"]] == ["uuid-1"]
        assert _body(by_name)["data"]["items"][0]["person_display"] == "爱丽丝"
        by_raw = _list(admin, skill_id=skill.id, person="wecom-zhang")
        assert [row["session_id"] for row in _body(by_raw)["data"]["items"]] == ["wx-1"]
        by_login = _list(admin, skill_id=skill.id, person="alice@domain.com")
        assert [row["session_id"] for row in _body(by_login)["data"]["items"]] == ["uuid-1"]

    def test_non_superuser_manager_lists_all_people(self):
        skill = _skill(team=[1], usage_team=[1, 2])
        web = _channel(skill)
        _conv(skill, web, session_id="mgr-web", external_user_id="alice@domain.com", title="网页问")
        _conv(skill, web, session_id="mgr-wx", external_user_id="wx-openid", title="企微问")
        manager = _normal(
            "skill_mgr",
            groups=[{"id": 1, "name": "T1"}],
            permission={"opspilot": {"skill_setting-View"}},
        )
        with patch("apps.core.utils.viewset_utils.AuthViewSet.get_has_permission", return_value=True):
            resp = _list(manager, skill_id=skill.id, current_team="1")
        assert resp.status_code == 200
        items = [row["session_id"] for row in _body(resp)["data"]["items"]]
        assert items == ["mgr-wx", "mgr-web"] or set(items) == {"mgr-web", "mgr-wx"}
        assert _body(resp)["data"]["count"] == 2

    def test_lists_newest_updated_first(self):
        skill = _skill()
        web = _channel(skill)
        older = _conv(skill, web, session_id="older-1", external_user_id="u1", title="旧")
        newer = _conv(skill, web, session_id="newer-1", external_user_id="u2", title="新")
        now = timezone.now()
        SkillConversation.objects.filter(pk=older.pk).update(updated_at=now - timedelta(hours=2))
        SkillConversation.objects.filter(pk=newer.pk).update(updated_at=now - timedelta(minutes=1))
        admin = _superuser()
        items = _body(_list(admin, skill_id=skill.id))["data"]["items"]
        assert [row["session_id"] for row in items] == ["newer-1", "older-1"]

    def test_title_search_does_not_scan_message_body(self):
        skill = _skill()
        web = _channel(skill)
        conv = _conv(skill, web, session_id="t-1", external_user_id="u", title="开权限申请")
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="磁盘空间不足")
        admin = _superuser()
        hit = _list(admin, skill_id=skill.id, title="开权限")
        assert [row["session_id"] for row in _body(hit)["data"]["items"]] == ["t-1"]
        miss = _list(admin, skill_id=skill.id, title="磁盘")
        assert _body(miss)["data"]["items"] == []

    def test_time_window_uses_refreshed_updated_at(self):
        skill = _skill()
        web = _channel(skill)
        conv = _conv(skill, web, session_id="old-1", external_user_id="u", title="旧标题")
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="旧标题")
        SkillConversation.objects.filter(pk=conv.pk).update(updated_at=timezone.now() - timedelta(days=2))
        admin = _superuser()
        start = (timezone.now() - timedelta(hours=24)).isoformat()
        hidden = _list(admin, skill_id=skill.id, start_time=start)
        assert _body(hidden)["data"]["items"] == []
        append_message(conv, SkillConversationMessage.ROLE_USER, "还在继续")
        shown = _list(admin, skill_id=skill.id, start_time=start)
        assert [row["session_id"] for row in _body(shown)["data"]["items"]] == ["old-1"]

    def test_admin_reads_other_user_messages_without_delete(self):
        skill = _skill()
        web = _channel(skill)
        conv = _conv(skill, web, session_id="own-1", external_user_id="owner@domain.com", title="你好")
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="你好智能体")
        SkillConversationMessage.objects.create(conversation=conv, role="assistant", content="收到")
        admin = _superuser()
        resp = _messages(admin, "own-1")
        assert resp.status_code == 200
        messages = _body(resp)["data"]["messages"]
        assert [row["conversation_content"] for row in messages] == ["你好智能体", "收到"]
        assert not hasattr(SkillChannelViewSet, "admin_conversation_delete")

    def test_user_delete_removes_row_from_admin_list(self):
        skill = _skill()
        web = _channel(skill)
        owner = _superuser("owner_del")
        uid = saas_external_user_id(owner)
        conv = _conv(skill, web, session_id="del-1", external_user_id=uid, title="要删")
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="要删")
        admin = _superuser("admin_del")
        delete_skill_session(session_id="del-1", external_user_id=uid)
        listed = _list(admin, skill_id=skill.id)
        assert _body(listed)["data"]["items"] == []
        missing = _messages(admin, "del-1")
        assert missing.status_code == 404

    def test_user_side_list_still_owner_scoped(self):
        skill = _skill()
        web = _channel(skill, enabled=True)
        owner = _superuser("hist_owner")
        other = _superuser("hist_other")
        uid = f"{owner.username}@{owner.domain}"
        _conv(skill, web, session_id="own-web", external_user_id=uid, title="我的")
        _conv(skill, web, session_id="other-web", external_user_id="wx-other", title="别人")
        factory = APIRequestFactory()
        request = factory.get("/skill_channel/conversations/", {"channel_id": web.id})
        request.user = owner
        request.COOKIES["current_team"] = "1"
        resp = opspilot_views.list_skill_channel_conversations(request)
        sessions = {row["session_id"] for row in json.loads(resp.content)["data"]}
        assert "own-web" in sessions
        assert "other-web" not in sessions
        other_msg = factory.get("/skill_channel/conversations/messages/", {"session_id": "own-web"})
        other_msg.user = other
        assert opspilot_views.list_skill_channel_session_messages(other_msg).status_code == 403

    def test_disabled_channel_history_still_listed(self):
        skill = _skill()
        web = _channel(skill, enabled=False, name="已下线")
        _conv(skill, web, session_id="off-1", external_user_id="u", title="下线后仍在")
        admin = _superuser()
        resp = _list(admin, skill_id=skill.id)
        items = _body(resp)["data"]["items"]
        assert items[0]["session_id"] == "off-1"
        assert items[0]["channel_name"] == "已下线"

    def test_empty_title_displays_new_session(self):
        skill = _skill()
        web = _channel(skill)
        empty = _conv(skill, web, session_id="empty-1", external_user_id="u", title="")
        SkillConversationMessage.objects.create(conversation=empty, role="user", content="磁盘空间不足")
        admin = _superuser()
        items = _body(_list(admin, skill_id=skill.id))["data"]["items"]
        assert items[0]["title"] == "新会话"
        assert items[0]["count"] == 1

    def test_requires_skill_id(self):
        admin = _superuser()
        resp = _list(admin)
        assert resp.status_code == 400

    def test_list_log_omits_filter_values(self, caplog):
        skill = _skill()
        web = _channel(skill)
        _conv(skill, web, session_id="log-1", external_user_id="secret-user", title="机密标题")
        admin = _superuser()
        caplog.set_level(logging.INFO, logger="opspilot")
        start = (timezone.now() - timedelta(hours=24)).isoformat()
        _list(
            admin,
            skill_id=skill.id,
            channel_id=web.id,
            person="secret-user",
            title="机密",
            start_time=start,
        )
        records = [record for record in caplog.records if record.msg == LIST_LOG_TEMPLATE]
        assert records
        formatted = records[0].msg % records[0].args
        assert "secret-user" not in formatted
        assert "机密" not in formatted
        assert records[0].args == (skill.id, web.id, 1, 1, 1, 1, 10, 1)

    def test_message_log_omits_payload(self, caplog):
        skill = _skill()
        web = _channel(skill)
        conv = _conv(skill, web, session_id="msg-log-1", external_user_id="owner@domain.com", title="你好")
        SkillConversationMessage.objects.create(conversation=conv, role="user", content="机密正文")
        admin = _superuser()
        caplog.set_level(logging.INFO, logger="opspilot")
        resp = _messages(admin, "msg-log-1")
        assert resp.status_code == 200
        records = [record for record in caplog.records if record.msg == MESSAGE_LOG_TEMPLATE]
        assert records
        formatted = records[0].msg % records[0].args
        assert "机密正文" not in formatted
        assert records[0].args == (skill.id, web.id, "msg-log-1")
