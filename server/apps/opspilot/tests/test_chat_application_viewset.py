"""ChatApplicationViewSet：会话列表/消息解析、技能引导 BFS、删除仅当前用户历史。"""
import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.opspilot.models import Bot, BotWorkFlow, ChatApplication, LLMSkill, WorkFlowConversationHistory
from apps.opspilot.viewsets.chat_application_view import ChatApplicationFilter, ChatApplicationViewSet

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _su(name="chat-app-admin"):
    return UserFactory(
        username=f"{name}-{uuid.uuid4().hex[:8]}",
        domain="domain.com",
        roles=[],
        is_superuser=True,
        group_list=[{"id": 1, "name": "T1"}],
    )


def _dispatch(action_name, method, *, data=None, query="", user=None):
    path = f"/{query}"
    if method == "post":
        request = factory.post(path, data=data or {}, format="json")
    else:
        request = factory.get(path)
    force_authenticate(request, user=user or _su())
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet.as_view({method: action_name})
    return view(request)


def test_filter_app_tags_contains_value_or_passthrough():
    qs_calls = {}

    class Dummy:
        def filter(self, **kwargs):
            qs_calls.update(kwargs)
            return "filtered"

    flt = ChatApplicationFilter()
    dummy = Dummy()
    assert flt.filter_app_tags(dummy, "app_tags", "") is dummy
    assert flt.filter_app_tags(dummy, "app_tags", "ops") == "filtered"
    assert qs_calls["app_tags__contains"] == ["ops"]


def test_web_chat_sessions_titles_and_truncation():
    user = _su("sess-user")
    bot = Bot.objects.create(name="sess-bot", team=[1])
    now = timezone.now()
    long_text = "问" * 60
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{user.username}@{user.domain}",
        conversation_role="user",
        conversation_content=long_text,
        conversation_time=now,
        entry_type="web_chat",
        session_id="s-long",
    )
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{user.username}@{user.domain}",
        conversation_role="user",
        conversation_content="短问",
        conversation_time=now - timedelta(minutes=1),
        entry_type="web_chat",
        session_id="s-short",
    )
    resp = _dispatch("web_chat_sessions", "get", query="?node_id=n1&bot_id=" + str(bot.id), user=user)
    items = resp.data
    by_sid = {i["session_id"]: i for i in items}
    assert by_sid["s-long"]["title"].endswith("...")
    assert by_sid["s-short"]["title"] == "短问"
    assert by_sid["s-long"]["bot_id"] == bot.id


def test_session_messages_requires_id_and_parses_json_content():
    missing = _dispatch("session_messages", "get")
    assert missing.status_code == 400
    user = _su("msg-user")
    bot = Bot.objects.create(name="msg-bot", team=[1])
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{user.username}@{user.domain}",
        conversation_role="user",
        conversation_content=json.dumps({"text": "hi"}),
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id="s1",
    )
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{user.username}@{user.domain}",
        conversation_role="bot",
        conversation_content="plain",
        conversation_time=timezone.now(),
        entry_type="web_chat",
        session_id="s1",
    )
    resp = _dispatch("session_messages", "get", query="?session_id=s1", user=user)
    contents = [i["conversation_content"] for i in resp.data]
    assert {"text": "hi"} in contents
    assert "plain" in contents


def test_skill_guide_bfs_finds_first_agent_and_handles_missing():
    missing_bot = _dispatch("skill_guide", "get", query="?node_id=n1")
    assert missing_bot.status_code == 400
    missing_node = _dispatch("skill_guide", "get", query="?bot_id=1")
    assert missing_node.status_code == 400

    bot = Bot.objects.create(name="guide-bot", team=[1])
    no_flow = _dispatch("skill_guide", "get", query=f"?bot_id={bot.id}&node_id=n1")
    assert no_flow.status_code == 404

    skill = LLMSkill.objects.create(name="guide-skill", team=[1], guide="欢迎使用")
    BotWorkFlow.objects.create(
        bot=bot,
        flow_json={
            "nodes": [
                {"id": "entry", "data": {"config": {}}},
                {"id": "llm", "data": {"config": {"agent": skill.id}}},
            ],
            "edges": [{"source": "entry", "target": "llm"}],
        },
    )
    ok = _dispatch("skill_guide", "get", query=f"?bot_id={bot.id}&node_id=entry")
    assert ok.data["guide"] == "欢迎使用"

    empty = _dispatch("skill_guide", "get", query=f"?bot_id={bot.id}&node_id=unknown")
    assert empty.data["guide"] == ""


def test_delete_session_history_only_current_user():
    user = _su("del-hist")
    other = _su("other-hist")
    bot = Bot.objects.create(name="del-bot", team=[1])
    now = timezone.now()
    mine = WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{user.username}@{user.domain}",
        conversation_role="user",
        conversation_content="mine",
        conversation_time=now,
        entry_type="web_chat",
        session_id="s-del",
    )
    theirs = WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="n1",
        user_id=f"{other.username}@{other.domain}",
        conversation_role="user",
        conversation_content="theirs",
        conversation_time=now,
        entry_type="web_chat",
        session_id="s-del",
    )
    missing = _dispatch("delete_session_history", "post", data={"session_id": "s-del"}, user=user)
    assert missing.status_code == 400
    ok = _dispatch("delete_session_history", "post", data={"node_id": "n1", "session_id": "s-del"}, user=user)
    assert ok.data["result"] is True
    assert not WorkFlowConversationHistory.objects.filter(id=mine.id).exists()
    assert WorkFlowConversationHistory.objects.filter(id=theirs.id).exists()


def test_get_queryset_guest_group_includes_guest_bots():
    guest = UserFactory(
        username=f"guest-app-{uuid.uuid4().hex[:8]}",
        domain="domain.com",
        roles=[],
        is_superuser=False,
        group_list=[{"id": 1, "name": "T1"}, {"id": 9, "name": "OpsPilotGuest"}],
    )
    bot_team = Bot.objects.create(name="team-bot", team=[1])
    bot_guest = Bot.objects.create(name="guest-bot", team=[9])
    ChatApplication.objects.create(bot=bot_team, node_id="n1", app_type="web_chat", app_name="a")
    ChatApplication.objects.create(bot=bot_guest, node_id="n2", app_type="web_chat", app_name="b")
    request = factory.get("/")
    request.user = guest
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet()
    view.request = request
    view.format_kwarg = None
    names = set(view.get_queryset().values_list("app_name", flat=True))
    assert names == {"a", "b"}
