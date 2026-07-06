"""NATS 触发节点「作为 web 对话（可选项）」特性测试。

覆盖：
1. BotWebChatSession 模型字段、is_participant 助手、ChatApplication 唯一约束调整
2. NATS 触发链路 expose=false/true 两种路径
3. ChatApplication.sync_applications_from_workflow 在 NATS 节点 expose 时的双发布
4. web 端 4 个 API 的参与者授权
"""

import json
import uuid
from unittest.mock import patch

import pytest
from django.db import IntegrityError

from apps.opspilot.models.bot_mgmt import Bot, BotWebChatSession, ChatApplication, WorkFlowConversationHistory


@pytest.fixture
def bot(db):
    """Create a minimal online Bot for testing."""
    return Bot.objects.create(
        name="test-bot",
        team=[1],
        online=True,
        created_by="tester",
        domain="test.com",
    )


# ============================================================================
# Section 3: NATS 触发链路 expose 分支
# ============================================================================


@pytest.fixture
def _patched_nats_engine(mocker):
    """Mock create_chat_flow_engine to inject a deterministic FakeAgentExecutor.

    Returns a helper that builds a BotWorkFlow with the given flow_json and
    returns the patched create_chat_flow_engine factory.
    """
    from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor
    from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine

    class _FakeAgentExecutor(BaseNodeExecutor):
        def execute(self, node_id, node_config, input_data):
            cfg = node_config.get("data", {}).get("config", {})
            input_key = cfg.get("inputParams", "last_message")
            output_key = cfg.get("outputParams", "last_message")
            received = input_data.get(input_key, "")
            return {output_key: f"agent_processed: {received}"}

    real_factory = create_chat_flow_engine

    def _factory(workflow, start_node_id, *args, **kwargs):
        engine = real_factory(workflow, start_node_id, *args, **kwargs)
        engine.custom_node_executors["agents"] = _FakeAgentExecutor(engine.variable_manager)
        return engine

    return mocker.patch("apps.opspilot.nats_api.create_chat_flow_engine", side_effect=_factory)


@pytest.mark.django_db(transaction=True)
def test_nats_trigger_without_expose_creates_no_session(bot, _patched_nats_engine):
    """NATS 节点 expose 缺省/false：不创建 BotWebChatSession，无 entry_type=nats 历史。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from apps.opspilot.nats_api import trigger_workflow_by_nats

    mocker = _patched_nats_engine
    flow_json = {
        "nodes": [
            {"id": "nats_entry", "type": "nats", "data": {"label": "NATS", "config": {}}},
            {
                "id": "agent_node",
                "type": "agents",
                "data": {"label": "Agent", "config": {"inputParams": "last_message", "outputParams": "last_message"}},
            },
        ],
        "edges": [{"source": "nats_entry", "target": "agent_node"}],
    }
    BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)

    result = trigger_workflow_by_nats(
        message="CPU 告警",
        team=2,
        user_ids=["alice", "bob"],
        bot_id=bot.id,
        node_id="nats_entry",
    )

    assert result["result"] is True
    assert "session_id" not in result
    assert result.get("exposed_as_web_chat") is not True
    assert BotWebChatSession.objects.count() == 0
    assert not WorkFlowConversationHistory.objects.filter(entry_type="nats").exists()


@pytest.mark.django_db(transaction=True)
def test_nats_trigger_with_expose_creates_session_and_history(bot, _patched_nats_engine):
    """NATS 节点 expose=true：创建 BotWebChatSession + 写 entry_type=nats 历史 + 返回 session_id。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from apps.opspilot.nats_api import trigger_workflow_by_nats

    flow_json = {
        "nodes": [
            {
                "id": "nats_entry",
                "type": "nats",
                "data": {
                    "label": "NATS",
                    "config": {"expose_as_web_chat": True, "outputParams": "last_message"},
                },
            },
            {
                "id": "agent_node",
                "type": "agents",
                "data": {"label": "Agent", "config": {"inputParams": "last_message", "outputParams": "last_message"}},
            },
        ],
        "edges": [{"source": "nats_entry", "target": "agent_node"}],
    }
    BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)

    result = trigger_workflow_by_nats(
        message="CPU 告警 - 这是一条非常长的告警消息用于测试标题截断" * 3,
        team=2,
        user_ids=["alice", "bob"],
        bot_id=bot.id,
        node_id="nats_entry",
    )

    assert result["result"] is True
    assert result.get("exposed_as_web_chat") is True
    assert "session_id" in result

    # BotWebChatSession 写入
    sess = BotWebChatSession.objects.get(session_id=result["session_id"])
    assert sess.bot_id == bot.id
    assert sess.node_id == "nats_entry"
    assert sess.source == "nats"
    assert sess.participants == ["alice", "bob"]
    assert sess.title  # 来自首条 user 消息
    assert len(sess.title) <= 53  # 50 字符 + "..."

    # WorkFlowConversationHistory 写入 entry_type=nats
    histories = WorkFlowConversationHistory.objects.filter(session_id=result["session_id"])
    assert histories.count() >= 1
    assert histories.filter(entry_type="nats", conversation_role="user").exists()
    assert histories.filter(conversation_role="user", user_id="alice").exists()


@pytest.mark.django_db(transaction=True)
def test_nats_trigger_with_expose_empty_user_ids_falls_back(bot, _patched_nats_engine):
    """expose=true 但 user_ids 全为空：不创建 BotWebChatSession，回退到旧路径。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from apps.opspilot.nats_api import trigger_workflow_by_nats

    flow_json = {
        "nodes": [
            {"id": "nats_entry", "type": "nats", "data": {"label": "NATS", "config": {"expose_as_web_chat": True}}},
            {
                "id": "agent_node",
                "type": "agents",
                "data": {"label": "Agent", "config": {"inputParams": "last_message", "outputParams": "last_message"}},
            },
        ],
        "edges": [{"source": "nats_entry", "target": "agent_node"}],
    }
    BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)

    result = trigger_workflow_by_nats(
        message="hi",
        team=2,
        user_ids=[],
        bot_id=bot.id,
        node_id="nats_entry",
    )
    assert result["result"] is True
    assert result.get("exposed_as_web_chat") is not True
    assert BotWebChatSession.objects.count() == 0


# ============================================================================
# Section 4: ChatApplication.sync_applications_from_workflow 双发布
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_sync_creates_two_chat_apps_when_nats_node_exposed(bot, mocker):
    """NATS 节点 expose=true 时 sync 产生 nats + web_chat 两条 ChatApplication。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow, ChatApplication

    # 屏蔽 BotWorkFlow.save() 内置 sync，避免 create 时已被调用
    mocker.patch("apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow", return_value=(0, 0, 0))
    flow_json = {
        "nodes": [
            {
                "id": "nats_entry",
                "type": "nats",
                "data": {
                    "label": "NATS",
                    "config": {"expose_as_web_chat": True, "appName": "NATS Alert", "appDescription": "alert entry"},
                },
            },
        ],
        "edges": [],
    }
    wf = BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)

    # 解除屏蔽后调用真正的 sync
    mocker.stopall()
    ChatApplication.sync_applications_from_workflow(wf)

    apps = list(ChatApplication.objects.filter(bot=bot, node_id="nats_entry"))
    types = sorted(a.app_type for a in apps)
    assert types == ["nats", "web_chat"]
    web_app = next(a for a in apps if a.app_type == "web_chat")
    assert web_app.app_name.startswith("[NATS] ")


@pytest.mark.django_db(transaction=True)
def test_sync_creates_only_nats_app_when_not_exposed(bot):
    """NATS 节点 expose=false/缺省时 sync 只产生 nats 一条。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow, ChatApplication

    flow_json = {
        "nodes": [
            {"id": "nats_entry", "type": "nats", "data": {"label": "NATS", "config": {}}},
        ],
        "edges": [],
    }
    wf = BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)
    ChatApplication.sync_applications_from_workflow(wf)

    apps = list(ChatApplication.objects.filter(bot=bot, node_id="nats_entry"))
    assert len(apps) == 1
    assert apps[0].app_type == "nats"


@pytest.mark.django_db(transaction=True)
def test_sync_web_chat_and_mobile_unchanged(bot):
    """web_chat / mobile 节点 sync 行为不变。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow, ChatApplication

    flow_json = {
        "nodes": [
            {"id": "wc", "type": "web_chat", "data": {"label": "WC", "config": {"appName": "MyApp", "appDescription": "d", "appIcon": "i"}}},
            {"id": "mb", "type": "mobile", "data": {"label": "MB", "config": {"appName": "MyMobile", "appDescription": "d", "appTags": ["x"]}}},
        ],
        "edges": [],
    }
    wf = BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)
    ChatApplication.sync_applications_from_workflow(wf)

    wc = ChatApplication.objects.get(bot=bot, node_id="wc")
    assert wc.app_type == "web_chat"
    assert wc.app_name == "MyApp"
    mb = ChatApplication.objects.get(bot=bot, node_id="mb")
    assert mb.app_type == "mobile"
    assert mb.app_name == "MyMobile"


@pytest.mark.django_db(transaction=True)
def test_sync_updates_existing_nats_exposed_web_chat(bot):
    """NATS 节点 expose=true 重复 sync：web_chat 应用走 update 分支。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow, ChatApplication

    flow_json = {
        "nodes": [
            {
                "id": "nats_entry",
                "type": "nats",
                "data": {
                    "label": "NATS",
                    "config": {"expose_as_web_chat": True, "appName": "V1"},
                },
            },
        ],
        "edges": [],
    }
    wf = BotWorkFlow.objects.create(bot=bot, flow_json=flow_json)

    # 第二次 sync：name 改了，应 update 已有 web_chat 应用
    wf.flow_json["nodes"][0]["data"]["config"]["appName"] = "V2"
    wf.save(update_fields=["flow_json"])
    ChatApplication.sync_applications_from_workflow(wf)

    web_app = ChatApplication.objects.get(bot=bot, node_id="nats_entry", app_type="web_chat")
    assert web_app.app_name == "[NATS] V2"


# ============================================================================
# Section 5: web 端 4 个 API 的参与者授权
# ============================================================================


def _make_user(username, group_ids=None, is_superuser=False):
    """构造 opspilot 测试用户。"""
    from apps.base.models import User

    if group_ids is None:
        group_ids = [1]
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": gid, "name": f"T{gid}"} for gid in group_ids],
        roles=["admin"] if is_superuser else ["normal"],
    )
    user.is_superuser = is_superuser
    user.save()
    # HasPermission 通过 request.user.permission[app_name] 判定；opspilot 模块以 app_name="opspilot" 查询
    user.permission = {"opspilot": {"bot_list-View"}}
    return user


def _get_chat_app_action(action_name, user, params=None):
    """直接调用 ChatApplicationViewSet 自定义 action。"""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.opspilot.viewsets.chat_application_view import ChatApplicationViewSet

    factory = APIRequestFactory()
    request = factory.get("/", data=params or {})
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet.as_view({"get": action_name})
    return view(request)


def _post_chat_app_action(action_name, user, body):
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.opspilot.viewsets.chat_application_view import ChatApplicationViewSet

    factory = APIRequestFactory()
    request = factory.post("/", data=body, format="json")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet.as_view({"post": action_name})
    return view(request)


@pytest.mark.django_db(transaction=True)
def test_web_chat_sessions_lists_participant_nats_session(bot):
    """web_chat_sessions：干系人 alice 能看到 NATS 会话。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-1",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice", "bob"],
        title="CPU 告警",
        created_by="nats",
    )

    alice = _make_user("alice")
    resp = _get_chat_app_action("web_chat_sessions", alice, {"bot_id": bot.id, "node_id": "nats_entry"})
    assert resp.status_code == 200
    data = resp.data
    nats_items = [it for it in data if it.get("session_id") == "nats-sess-1"]
    assert len(nats_items) == 1
    item = nats_items[0]
    assert item["title"] == "CPU 告警"
    assert item["bot_id"] == bot.id
    assert item["source"] == "nats"


@pytest.mark.django_db(transaction=True)
def test_web_chat_sessions_hides_non_participant_nats_session(bot):
    """web_chat_sessions：非干系人 charlie 看不到 NATS 会话。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-2",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice", "bob"],
    )

    charlie = _make_user("charlie")
    resp = _get_chat_app_action("web_chat_sessions", charlie, {"bot_id": bot.id, "node_id": "nats_entry"})
    assert resp.status_code == 200
    assert all(it.get("session_id") != "nats-sess-2" for it in resp.data)


@pytest.mark.django_db(transaction=True)
def test_session_messages_returns_history_for_participant(bot):
    """session_messages：干系人 alice 能取到全部消息（含 entry_type=nats）。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-3",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice"],
    )
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="nats_entry",
        user_id="alice",
        conversation_role="user",
        conversation_content="original alert",
        conversation_time="2026-01-01T00:00:00Z",
        entry_type="nats",
        session_id="nats-sess-3",
    )
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="nats_entry",
        user_id="bot",
        conversation_role="bot",
        conversation_content="bot reply",
        conversation_time="2026-01-01T00:00:01Z",
        entry_type="nats",
        session_id="nats-sess-3",
    )

    alice = _make_user("alice")
    resp = _get_chat_app_action("session_messages", alice, {"session_id": "nats-sess-3"})
    assert resp.status_code == 200
    assert len(resp.data) == 2


@pytest.mark.django_db(transaction=True)
def test_session_messages_forbidden_for_non_participant(bot):
    """session_messages：非干系人 charlie 返回 403。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-4",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice"],
    )

    charlie = _make_user("charlie")
    resp = _get_chat_app_action("session_messages", charlie, {"session_id": "nats-sess-4"})
    assert resp.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_delete_session_soft_deletes_for_participant(bot):
    """delete_session_history：干系人 alice 删除成功（软删）。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-5",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice"],
    )
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="nats_entry",
        user_id="alice",
        conversation_role="user",
        conversation_content="x",
        conversation_time="2026-01-01T00:00:00Z",
        entry_type="nats",
        session_id="nats-sess-5",
    )

    alice = _make_user("alice")
    resp = _post_chat_app_action(
        "delete_session_history",
        alice,
        {"node_id": "nats_entry", "session_id": "nats-sess-5"},
    )
    assert resp.status_code == 200
    sess = BotWebChatSession.objects.get(session_id="nats-sess-5")
    assert sess.is_active is False
    assert WorkFlowConversationHistory.objects.filter(session_id="nats-sess-5").count() == 0


@pytest.mark.django_db(transaction=True)
def test_delete_session_forbidden_for_non_participant(bot):
    """delete_session_history：非干系人 charlie 返回 403。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-6",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice"],
    )

    charlie = _make_user("charlie")
    resp = _post_chat_app_action(
        "delete_session_history",
        charlie,
        {"node_id": "nats_entry", "session_id": "nats-sess-6"},
    )
    assert resp.status_code == 403
    assert BotWebChatSession.objects.get(session_id="nats-sess-6").is_active is True


@pytest.mark.django_db(transaction=True)
def test_multiple_participants_share_session_id(bot):
    """NATS 入参 3 个 user_ids 时，3 个干系人都能从同一 session_id 看到会话。"""
    BotWebChatSession.objects.create(
        session_id="nats-sess-7",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["u1", "u2", "u3"],
    )

    for username in ("u1", "u2", "u3"):
        u = _make_user(username)
        resp = _get_chat_app_action("web_chat_sessions", u, {"bot_id": bot.id, "node_id": "nats_entry"})
        assert resp.status_code == 200
        ids = [it.get("session_id") for it in resp.data]
        assert "nats-sess-7" in ids

    outsider = _make_user("u9")
    resp = _get_chat_app_action("web_chat_sessions", outsider, {"bot_id": bot.id, "node_id": "nats_entry"})
    ids = [it.get("session_id") for it in resp.data]
    assert "nats-sess-7" not in ids


# ============================================================================
# Section 1: BotWebChatSession 模型
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_bot_web_chat_session_create_and_persistence():
    """BotWebChatSession 能正常创建并持久化全部字段。"""
    session = BotWebChatSession.objects.create(
        session_id="abc123",
        bot_id=42,
        node_id="nats_entry",
        source="nats",
        participants=["alice", "bob"],
        title="CPU 告警",
        created_by="nats",
    )
    assert session.session_id == "abc123"
    assert session.bot_id == 42
    assert session.node_id == "nats_entry"
    assert session.source == "nats"
    assert session.participants == ["alice", "bob"]
    assert session.title == "CPU 告警"
    assert session.created_by == "nats"
    assert session.is_active is True
    assert session.created_at is not None
    assert session.updated_at is not None


@pytest.mark.django_db(transaction=True)
def test_bot_web_chat_session_is_participant_username_only():
    """is_participant 接受纯 username 字符串。"""
    session = BotWebChatSession.objects.create(
        session_id="s1",
        bot_id=1,
        node_id="n1",
        participants=["alice", "bob"],
    )
    assert session.is_participant("alice") is True
    assert session.is_participant("bob") is True
    assert session.is_participant("charlie") is False


@pytest.mark.django_db(transaction=True)
def test_bot_web_chat_session_is_participant_username_at_domain():
    """is_participant 接受 'username@domain' 格式。"""
    session = BotWebChatSession.objects.create(
        session_id="s2",
        bot_id=1,
        node_id="n1",
        participants=["alice", "bob"],
    )
    assert session.is_participant("alice@example.com") is True
    assert session.is_participant("bob@example.com") is True
    assert session.is_participant("charlie@example.com") is False


@pytest.mark.django_db(transaction=True)
def test_bot_web_chat_session_is_participant_accepts_dict_user():
    """is_participant 接受 dict 类 user 对象（含 username/domain）。"""
    session = BotWebChatSession.objects.create(
        session_id="s3",
        bot_id=1,
        node_id="n1",
        participants=["alice"],
    )
    user_dict = {"username": "alice", "domain": "example.com"}
    assert session.is_participant(user_dict) is True

    other_dict = {"username": "charlie", "domain": "example.com"}
    assert session.is_participant(other_dict) is False


@pytest.mark.django_db(transaction=True)
def test_bot_web_chat_session_ordering_by_created_at_desc():
    """列表查询按 created_at 倒序排列。"""
    s1 = BotWebChatSession.objects.create(session_id="s_old", bot_id=1, node_id="n", participants=[])
    s2 = BotWebChatSession.objects.create(session_id="s_new", bot_id=1, node_id="n", participants=[])
    rows = list(BotWebChatSession.objects.filter(bot_id=1, node_id="n").order_by("-created_at"))
    assert rows[0].session_id == "s_new"
    assert rows[1].session_id == "s_old"


# ============================================================================
# Section 2: ChatApplication 唯一约束调整
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_chat_application_unique_together_includes_app_type(bot):
    """ChatApplication 唯一约束由 [bot, node_id] 调整为 [bot, node_id, app_type]。

    同一 bot+node 上允许同时存在 nats 与 web_chat 两条应用。
    """
    ChatApplication.objects.create(
        bot=bot,
        node_id="nats_entry",
        app_type=ChatApplication.APP_TYPE_NATS,
        app_name="NATS app",
    )
    # 不应抛 IntegrityError：app_type 不同
    ChatApplication.objects.create(
        bot=bot,
        node_id="nats_entry",
        app_type=ChatApplication.APP_TYPE_WEB_CHAT,
        app_name="Web chat app",
    )
    assert ChatApplication.objects.filter(bot=bot, node_id="nats_entry").count() == 2


@pytest.mark.django_db(transaction=True)
def test_chat_application_same_app_type_conflict(bot):
    """同一 bot+node+app_type 仍走唯一约束。"""
    ChatApplication.objects.create(
        bot=bot,
        node_id="nats_entry",
        app_type=ChatApplication.APP_TYPE_NATS,
        app_name="NATS app",
    )
    with pytest.raises(IntegrityError):
        ChatApplication.objects.create(
            bot=bot,
            node_id="nats_entry",
            app_type=ChatApplication.APP_TYPE_NATS,
            app_name="Duplicate",
        )
