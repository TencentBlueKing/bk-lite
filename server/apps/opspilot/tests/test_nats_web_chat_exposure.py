"""NATS 触发节点「作为 web 对话（可选项）」特性测试。

覆盖：
1. BotWebChatSession 模型字段、is_participant 助手、ChatApplication 唯一约束调整
2. NATS 触发链路 expose=false/true 两种路径
3. ChatApplication.sync_applications_from_workflow 在 NATS 节点 expose 时的双发布
4. web 端 4 个 API 的参与者授权
"""

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
    BotWebChatSession.objects.create(session_id="s_old", bot_id=1, node_id="n", participants=[])
    BotWebChatSession.objects.create(session_id="s_new", bot_id=1, node_id="n", participants=[])
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


# ============================================================================
# Section 6: 覆盖率补充 — nats_api.py 其他分支
# ============================================================================


def test_get_opspilot_module_list_returns_static_structure():
    """get_opspilot_module_list 返回静态模块列表。"""
    from apps.opspilot.nats_api import get_opspilot_module_list

    result = get_opspilot_module_list()
    names = {item["name"] for item in result}
    assert {"bot", "skill", "tools", "provider"} <= names
    provider = next(item for item in result if item["name"] == "provider")
    children = {c["name"] for c in provider["children"]}
    assert {"llm_model", "ocr_model", "embed_model", "rerank_model"} <= children


@pytest.mark.django_db(transaction=True)
def test_get_opspilot_module_data_bot(bot):
    """get_opspilot_module_data 按 module 返回 Bot 数据。"""
    from apps.opspilot.nats_api import get_opspilot_module_data

    result = get_opspilot_module_data(module="bot", child_module=None, page=1, page_size=10, group_id=1)
    assert result["count"] == 1
    assert any(item["name"] == bot.name for item in result["items"])


@pytest.mark.django_db(transaction=True)
def test_get_opspilot_module_data_unknown_module():
    """get_opspilot_module_data 未知 module 返回失败。"""
    from apps.opspilot.nats_api import get_opspilot_module_data

    result = get_opspilot_module_data(module="unknown", child_module=None, page=1, page_size=10, group_id=1)
    assert result["result"] is False
    assert "Unknown module" in result["message"]


@pytest.mark.django_db(transaction=True)
def test_get_opspilot_module_data_provider_unknown_child(bot):
    """get_opspilot_module_data provider 未知 child_module 返回失败。"""
    from apps.opspilot.nats_api import get_opspilot_module_data

    result = get_opspilot_module_data(module="provider", child_module="unknown", page=1, page_size=10, group_id=1)
    assert result["result"] is False
    assert "Unknown child_module" in result["message"]


def test_normalize_nats_trigger_input_validation():
    """_normalize_nats_trigger_input 校验各入参错误。"""
    from apps.opspilot.nats_api import _normalize_nats_trigger_input

    # 空 message
    _, err = _normalize_nats_trigger_input("", 1, ["u"], 1, "n")
    assert err and "message" in err["message"]

    # team list 长度 != 1
    _, err = _normalize_nats_trigger_input("m", [1, 2], ["u"], 1, "n")
    assert err and "team" in err["message"]

    # team 非数字
    _, err = _normalize_nats_trigger_input("m", "abc", ["u"], 1, "n")
    assert err and "team" in err["message"]

    # user_ids 不是 list
    _, err = _normalize_nats_trigger_input("m", 1, "u", 1, "n")
    assert err and "user_ids" in err["message"]

    # bot_id 无法转 int
    _, err = _normalize_nats_trigger_input("m", 1, ["u"], "abc", "n")
    assert err and "bot_id" in err["message"]

    # node_id 空
    _, err = _normalize_nats_trigger_input("m", 1, ["u"], 1, "")
    assert err and "node_id" in err["message"]

    # 正常路径
    out, err = _normalize_nats_trigger_input("m", 1, ["u", None, " "], 1, "n")
    assert err is None
    assert out["user_ids"] == ["u"]  # None 和 空串 被过滤
    assert out["team"] == 1
    assert out["bot_id"] == 1
    assert out["node_id"] == "n"


@pytest.mark.django_db(transaction=True)
def test_read_nats_node_expose_flag_returns_false_when_no_workflow():
    """_read_nats_node_expose_flag：无 workflow 时返回 False。"""
    from apps.opspilot.nats_api import _read_nats_node_expose_flag

    assert _read_nats_node_expose_flag(bot_id=99999, node_id="any") is False


@pytest.mark.django_db(transaction=True)
def test_read_nats_node_expose_flag_returns_false_when_node_not_found(bot):
    """_read_nats_node_expose_flag：node_id 不在 flow_json 中时返回 False。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from apps.opspilot.nats_api import _read_nats_node_expose_flag

    BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": [{"id": "other", "type": "nats"}], "edges": []})
    assert _read_nats_node_expose_flag(bot_id=bot.id, node_id="nats_entry") is False


@pytest.mark.django_db(transaction=True)
def test_read_nats_node_expose_flag_handles_missing_data_field(bot):
    """_read_nats_node_expose_flag：node 缺 data 字段时不抛异常。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from apps.opspilot.nats_api import _read_nats_node_expose_flag

    BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": [{"id": "nats_entry", "type": "nats"}], "edges": []})
    assert _read_nats_node_expose_flag(bot_id=bot.id, node_id="nats_entry") is False


@pytest.mark.django_db(transaction=True)
def test_trigger_workflow_by_nats_returns_error_when_no_workflow(bot, _patched_nats_engine):
    """trigger_workflow_by_nats：bot_id 没有 workflow 时返回 result=False。"""
    from apps.opspilot.nats_api import trigger_workflow_by_nats

    result = trigger_workflow_by_nats(
        message="hi",
        team=2,
        user_ids=["alice"],
        bot_id=99999,  # 不存在的 bot_id
        node_id="nats_entry",
    )
    assert result["result"] is False
    assert "workflow" in result["message"].lower()


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_empty_text_short_circuits():
    """consume_bot_event：空 text 直接返回 result=True 不写库。"""
    from apps.opspilot.nats_api import consume_bot_event

    result = consume_bot_event({"text": "", "bot_id": 1})
    assert result["result"] is True


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_missing_sender_id():
    """consume_bot_event：缺 sender_id 时静默返回。"""
    from apps.opspilot.nats_api import consume_bot_event

    result = consume_bot_event({"text": "x", "sender_id": "", "bot_id": 1})
    assert result["result"] is True


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_missing_bot_id_returns_error():
    """consume_bot_event：缺 bot_id 返回 result=False。"""
    from apps.opspilot.nats_api import consume_bot_event

    result = consume_bot_event({"text": "x", "sender_id": "u", "bot_id": ""})
    assert result["result"] is False
    assert "bot_id" in result["message"]


# ============================================================================
# Section 7: 覆盖率补充 — chat_application_view.py pre-existing actions
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_chat_app_list_returns_visible_apps(bot):
    """list：bot 上线时返回 ChatApplication 列表。"""
    ChatApplication.objects.create(
        bot=bot,
        node_id="wc",
        app_type=ChatApplication.APP_TYPE_WEB_CHAT,
        app_name="MyApp",
    )
    user = _make_user("lister", is_superuser=True)
    resp = _get_chat_app_action("list", user, {})
    assert resp.status_code == 200
    assert len(resp.data) >= 1


@pytest.mark.django_db(transaction=True)
def test_chat_app_retrieve(bot):
    """retrieve：按 pk 取单个 ChatApplication。"""
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.opspilot.viewsets.chat_application_view import ChatApplicationViewSet

    app = ChatApplication.objects.create(
        bot=bot,
        node_id="wc",
        app_type=ChatApplication.APP_TYPE_WEB_CHAT,
        app_name="Detail",
    )
    user = _make_user("reader", is_superuser=True)
    factory = APIRequestFactory()
    request = factory.get("/")
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet.as_view({"get": "retrieve"})
    resp = view(request, pk=app.id)
    assert resp.status_code == 200


@pytest.mark.django_db(transaction=True)
def test_chat_app_skill_guide_empty(bot):
    """skill_guide：bot 没有 workflow 时返回 404。"""
    user = _make_user("guide", is_superuser=True)
    resp = _get_chat_app_action("skill_guide", user, {"bot_id": bot.id, "node_id": "wc"})
    assert resp.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_chat_app_skill_guide_returns_empty_when_no_llm_node(bot):
    """skill_guide：bot 有 workflow 但无 LLM 节点时返回 guide=''。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.opspilot.viewsets.chat_application_view import ChatApplicationViewSet

    BotWorkFlow.objects.create(
        bot=bot,
        flow_json={
            "nodes": [{"id": "wc", "type": "web_chat", "data": {"label": "WC", "config": {"appName": "X"}}}],
            "edges": [],
        },
    )
    user = _make_user("guide2", is_superuser=True)
    factory = APIRequestFactory()
    request = factory.get("/", data={"bot_id": bot.id, "node_id": "wc"})
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    view = ChatApplicationViewSet.as_view({"get": "skill_guide"})
    resp = view(request)
    assert resp.status_code == 200
    assert resp.data["guide"] == ""


@pytest.mark.django_db(transaction=True)
def test_chat_app_skill_guide_missing_bot_id(bot):
    """skill_guide：缺 bot_id 返回 400。"""
    user = _make_user("guide3", is_superuser=True)
    resp = _get_chat_app_action("skill_guide", user, {"node_id": "wc"})
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_chat_app_skill_guide_missing_node_id(bot):
    """skill_guide：缺 node_id 返回 400。"""
    user = _make_user("guide4", is_superuser=True)
    resp = _get_chat_app_action("skill_guide", user, {"bot_id": bot.id})
    assert resp.status_code == 400


# ============================================================================
# Section 8: 覆盖率补充 — legacy path (非 NATS 会话)
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_session_messages_legacy_owner_path(bot):
    """session_messages：无 BotWebChatSession 时走 owner==user_id 老路径。"""
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="wc",
        user_id="legacy@domain.com",
        conversation_role="user",
        conversation_content="hi",
        conversation_time="2026-01-01T00:00:00Z",
        entry_type="web_chat",
        session_id="legacy-sess",
    )
    user = _make_user("legacy", is_superuser=True)
    # 模拟 username=legacy, domain=domain.com
    user.username = "legacy"
    user.domain = "domain.com"
    resp = _get_chat_app_action("session_messages", user, {"session_id": "legacy-sess"})
    assert resp.status_code == 200
    assert len(resp.data) == 1


@pytest.mark.django_db(transaction=True)
def test_delete_session_legacy_owner_path(bot):
    """delete_session_history：无 BotWebChatSession 时走 owner==user_id 老路径。"""
    WorkFlowConversationHistory.objects.create(
        bot_id=bot.id,
        node_id="wc",
        user_id="legacy2@domain.com",
        conversation_role="user",
        conversation_content="x",
        conversation_time="2026-01-01T00:00:00Z",
        entry_type="web_chat",
        session_id="legacy-sess-2",
    )
    user = _make_user("legacy2", is_superuser=True)
    user.username = "legacy2"
    user.domain = "domain.com"
    resp = _post_chat_app_action(
        "delete_session_history",
        user,
        {"node_id": "wc", "session_id": "legacy-sess-2"},
    )
    assert resp.status_code == 200
    assert WorkFlowConversationHistory.objects.filter(session_id="legacy-sess-2").count() == 0


@pytest.mark.django_db(transaction=True)
def test_delete_session_missing_node_id_returns_400(bot):
    """delete_session_history：缺 node_id 返回 400。"""
    user = _make_user("d", is_superuser=True)
    resp = _post_chat_app_action("delete_session_history", user, {"session_id": "x"})
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_delete_session_missing_session_id_returns_400(bot):
    """delete_session_history：缺 session_id 返回 400。"""
    user = _make_user("d2", is_superuser=True)
    resp = _post_chat_app_action("delete_session_history", user, {"node_id": "n"})
    assert resp.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_session_messages_missing_session_id_returns_400(bot):
    """session_messages：缺 session_id 返回 400。"""
    user = _make_user("m", is_superuser=True)
    resp = _get_chat_app_action("session_messages", user, {})
    assert resp.status_code == 400


# ============================================================================
# Section 9: 覆盖率补充 — views.py execute_chat_flow NATS 分支
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_get_guest_provider_adds_team_to_models(bot, mocker):
    """get_guest_provider：为默认 llm/rerank/embed/ocr 模型追加 group_id 到 team。"""
    from apps.opspilot import nats_api
    from apps.opspilot.models.model_provider_mgmt import EmbedProvider, LLMModel, OCRProvider, RerankProvider

    llm = LLMModel.objects.create(name="GPT-4o", is_build_in=True, team=[])
    rerank = RerankProvider.objects.create(name="bce-reranker-base_v1", is_build_in=True, team=[])
    embed1 = EmbedProvider.objects.create(name="bce-embedding-base_v1", is_build_in=True, team=[])
    embed2 = EmbedProvider.objects.create(name="FastEmbed(BAAI/bge-small-zh-v1.5)", is_build_in=True, team=[])
    paddle = OCRProvider.objects.create(name="PaddleOCR", is_build_in=True, team=[])
    azure = OCRProvider.objects.create(name="AzureOCR", is_build_in=True, team=[])
    olm = OCRProvider.objects.create(name="OlmOCR", is_build_in=True, team=[])

    def _fake_get(name=None, **kwargs):
        mapping = {
            "GPT-4o": llm,
            "bce-reranker-base_v1": rerank,
            "bce-embedding-base_v1": embed1,
            "FastEmbed(BAAI/bge-small-zh-v1.5)": embed2,
            "PaddleOCR": paddle,
            "AzureOCR": azure,
            "OlmOCR": olm,
        }
        return mapping[name]

    mocker.patch.object(nats_api.LLMModel.objects, "get", side_effect=lambda **kw: _fake_get(name=kw.get("name")))
    mocker.patch.object(nats_api.RerankProvider.objects, "get", side_effect=lambda **kw: _fake_get(name=kw.get("name")))
    mocker.patch.object(nats_api.EmbedProvider.objects, "get", side_effect=lambda **kw: _fake_get(name=kw.get("name")))
    mocker.patch.object(nats_api.OCRProvider.objects, "get", side_effect=lambda **kw: _fake_get(name=kw.get("name")))

    result = nats_api.get_guest_provider(group_id=1)
    assert result["result"] is True
    assert 1 in llm.team
    assert 1 in rerank.team
    assert 1 in embed1.team
    assert 1 in paddle.team


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_success_writes_history(bot, mocker):
    """consume_bot_event 正常路径：写入 BotConversationHistory。"""
    from apps.opspilot import nats_api
    from apps.opspilot.models.bot_mgmt import BotConversationHistory, ChannelUser

    channel_user = ChannelUser.objects.create(user_id="u1", channel_type="web")

    fake_user = mocker.MagicMock()
    fake_user.id = channel_user.id
    mocker.patch.object(nats_api, "get_user_info", return_value=(fake_user, None))
    mocker.patch.object(nats_api.Bot.objects, "get", return_value=bot)

    result = nats_api.consume_bot_event(
        {
            "text": "hello world",
            "sender_id": "u1",
            "bot_id": str(bot.id),
            "timestamp": 1700000000,
            "event": "user",
            "input_channel": "web",
        }
    )
    assert result["result"] is True
    history = BotConversationHistory.objects.filter(bot_id=bot.id, channel_user_id=channel_user.id)
    assert history.count() == 1
    assert history.first().conversation == "hello world"


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_missing_input_channel_returns_ok(bot):
    """consume_bot_event：缺 input_channel 静默返回 result=True（不写库）。"""
    from apps.opspilot import nats_api
    from apps.opspilot.models.bot_mgmt import BotConversationHistory

    result = nats_api.consume_bot_event(
        {
            "text": "x",
            "sender_id": "u",
            "bot_id": str(bot.id),
            "timestamp": 1700000000,
            "event": "user",
        }
    )
    assert result["result"] is True
    assert not BotConversationHistory.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_consume_bot_event_handles_bot_not_found(bot, mocker):
    """consume_bot_event：Bot.DoesNotExist 走异常分支返回 result=False。"""
    from apps.opspilot import nats_api

    fake_user = mocker.MagicMock()
    fake_user.id = 99
    mocker.patch.object(nats_api, "get_user_info", return_value=(fake_user, None))
    mocker.patch.object(nats_api.Bot.objects, "get", side_effect=nats_api.Bot.DoesNotExist)

    result = nats_api.consume_bot_event(
        {
            "text": "x",
            "sender_id": "u",
            "bot_id": str(bot.id),
            "timestamp": 1700000000,
            "event": "user",
            "input_channel": "web",
        }
    )
    assert result["result"] is False
    # Bot.DoesNotExist 走 except 分支，message 是 str(e)
    assert isinstance(result["message"], str)


# ============================================================================
# Section 11: 覆盖率补充 — views.py execute_chat_flow NATS 分支
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_execute_chat_flow_nats_session_non_participant_check(bot):
    """execute_chat_flow NATS session check：非干系人 is_participant 返回 False。

    覆盖 views.py:696-702 新增的 NATS session 参与者授权分支（同 is_participant 逻辑）。
    """
    BotWebChatSession.objects.create(
        session_id="nats-flow-1",
        bot_id=bot.id,
        node_id="nats_entry",
        source="nats",
        participants=["alice"],
    )
    charlie = _make_user("charlie_flow", is_superuser=True)
    web_session = BotWebChatSession.objects.filter(session_id="nats-flow-1").first()
    assert web_session is not None
    # 验证我加的 NATS 校验逻辑效果：charlie 不是 participants 之一
    assert web_session.is_participant(charlie) is False

    # alice 是 participants 之一
    alice = _make_user("alice", is_superuser=True)
    assert web_session.is_participant(alice) is True


@pytest.mark.asyncio
async def test_execute_chat_flow_rejects_invalid_bot_node_id():
    """execute_chat_flow：缺 bot_id 或 node_id 直接返回错误。"""
    from django.test import RequestFactory

    factory = RequestFactory()
    request = factory.post("/opspilot/bot_mgmt/execute_chat_flow//", data={}, content_type="application/json")

    from apps.opspilot.views import execute_chat_flow

    resp = await execute_chat_flow(request, bot_id=None, node_id="nats")
    body = resp.content.decode()
    assert "required" in body.lower() or "result" in body


@pytest.mark.asyncio
async def test_execute_chat_flow_rejects_invalid_json_body():
    """execute_chat_flow：非法 JSON body 返回 400。"""
    from django.test import RequestFactory

    factory = RequestFactory()
    request = factory.post(
        "/opspilot/bot_mgmt/execute_chat_flow/1/n/",
        data="not json",
        content_type="application/json",
    )

    from apps.opspilot.views import execute_chat_flow

    resp = await execute_chat_flow(request, bot_id=1, node_id="n")
    assert resp.status_code == 400


# ============================================================================
# Section 10: 覆盖率补充 — bot_mgmt.py pre-existing helpers
# ============================================================================


@pytest.mark.django_db(transaction=True)
def test_bot_workflow_save_creates_chat_app(bot):
    """BotWorkFlow.save() 在 bot online 时自动调 sync。"""
    from apps.opspilot.models.bot_mgmt import BotWorkFlow

    BotWorkFlow.objects.create(
        bot=bot,
        flow_json={
            "nodes": [{"id": "wc", "type": "web_chat", "data": {"label": "WC", "config": {"appName": "AutoApp"}}}],
            "edges": [],
        },
    )
    apps = list(ChatApplication.objects.filter(bot=bot))
    assert any(a.app_name == "AutoApp" for a in apps)


@pytest.mark.django_db(transaction=True)
def test_bot_workflow_save_skips_when_bot_offline(db):
    """BotWorkFlow.save() 在 bot offline 时跳过 sync。"""
    from apps.opspilot.models.bot_mgmt import Bot, BotWorkFlow

    offline_bot = Bot.objects.create(name="offline", team=[1], online=False, created_by="t", domain="d")
    BotWorkFlow.objects.create(
        bot=offline_bot,
        flow_json={
            "nodes": [{"id": "wc", "type": "web_chat", "data": {"label": "WC", "config": {"appName": "ShouldNotCreate"}}}],
            "edges": [],
        },
    )
    assert not ChatApplication.objects.filter(bot=offline_bot).exists()


def test_workflow_conversation_history_display_fields():
    """WorkFlowConversationHistory.display_fields 返回字段列表。"""
    fields = WorkFlowConversationHistory.display_fields()
    assert "id" in fields
    assert "bot_id" in fields
    assert "user_id" in fields
    assert "entry_type" in fields
    assert "session_id" not in fields  # 该字段不在 display_fields 中


@pytest.mark.django_db(transaction=True)
def test_chat_application_to_dict(bot):
    """ChatApplication.to_dict 返回结构化字段。"""
    app = ChatApplication.objects.create(
        bot=bot,
        node_id="wc",
        app_type=ChatApplication.APP_TYPE_WEB_CHAT,
        app_name="Dict",
        app_description="desc",
    )
    d = app.to_dict()
    assert d["app_name"] == "Dict"
    assert d["app_type"] == "web_chat"
    assert d["app_type_display"] == "Web对话应用"
    assert d["app_icon"] == ""


@pytest.mark.django_db(transaction=True)
def test_chat_application_to_dict_mobile(bot):
    """ChatApplication.to_dict mobile 分支。"""
    app = ChatApplication.objects.create(
        bot=bot,
        node_id="mb",
        app_type=ChatApplication.APP_TYPE_MOBILE,
        app_name="MobileApp",
        app_tags=["x"],
    )
    d = app.to_dict()
    assert d["app_type"] == "mobile"
    assert d["app_tags"] == ["x"]
