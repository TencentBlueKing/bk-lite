"""对话确认后新建技能包：只认确认卡，不改已选技能包。"""

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import override_settings
from langchain_core.messages import AIMessage

from apps.opspilot.metis.llm.agent.tool_execution_planner import (
    ToolExecutionPlan,
    enforce_prepare_conversation_skill_package,
)
from apps.opspilot.metis.llm.chain.deepagent_assembly import DeepAgentAssemblyMixin
from apps.opspilot.metis.llm.middleware.conversation_skill_package import ConversationSkillPackageMiddleware
from apps.opspilot.models import LLMSkill, SkillPackage
from apps.opspilot.services.conversation_skill_package import (
    AUTHORING_EXTRA_KEY,
    AUTHORING_PROMPT_SUFFIX,
    PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
    authoring_context,
    prepare_conversation_skill_package,
    publish_conversation_skill_package_choice,
    try_commit_conversation_skill_package,
    user_can_add_skill_package,
    user_requested_skill_package,
)
from apps.opspilot.services.skill_package.runtime import hydrate_skill_packages
from apps.opspilot.utils import agui_chat
from apps.opspilot.utils.pending_question import PENDING_QUESTION_PREFIX, PENDING_QUESTION_TTL_SECONDS, peek_pending_question

_LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "conversation-skill-package-tests",
    }
}
_BODY = "步骤：\n1. 查看磁盘剩余空间\nSECRET_BODY_SENTINEL\n完成：用户看到剩余空间。"


@pytest.fixture(autouse=True)
def _locmem_cache():
    with override_settings(CACHES=_LOCMEM):
        cache.clear()
        yield
        cache.clear()


def _user(**overrides):
    payload = {
        "username": "alice",
        "id": 7,
        "domain": "example.com",
        "is_superuser": False,
        "is_authenticated": True,
        "permission": {"opspilot": {"tool_list-Add"}},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _request(skill, message, authoring, history=None, thread_id="thread-1"):
    return SimpleNamespace(
        extra_config={
            "skill_id": skill.id,
            "conversation_key": f"thread:{thread_id}",
            "thread_id": thread_id,
            AUTHORING_EXTRA_KEY: authoring,
        },
        user_message=message,
        chat_history=history or [],
        thread_id=thread_id,
    )


def _config(request):
    return {
        "configurable": {
            "thread_id": request.thread_id,
            "graph_request": request,
            "execution_id": "exec-1",
            "node_id": "skill_test",
        }
    }


def _skill(**overrides):
    payload = {"name": "agent", "team": [3, 8], "skill_packages": ["keep-me"]}
    payload.update(overrides)
    return LLMSkill.objects.create(**payload)


def _issue(skill, authoring=None, message="请把查磁盘做成技能包", **fields):
    authoring = authoring if authoring is not None else authoring_context(_user(), "skill_test")
    request = _request(skill, message, authoring, history=fields.pop("history", None), thread_id=fields.pop("thread_id", "thread-1"))
    prepared = prepare_conversation_skill_package(
        name=fields.get("name", "查磁盘"),
        description=fields.get("description", "磁盘快满时使用"),
        triggers=fields.get("triggers", ["磁盘", "磁盘", "空间"]),
        skill_markdown=fields.get("skill_markdown", _BODY),
        graph_request=request,
        config=_config(request),
    )
    if prepared.get("ok"):
        publish_conversation_skill_package_choice(
            prepared,
            graph_request=request,
            config=_config(request),
            messages=[],
            tool_call_id="call-draft",
        )
    return prepared, request


def _confirm_params(skill, draft, **overrides):
    params = {
        "thread_id": "thread-1",
        "skill_id": skill.id,
        "choice_id": draft["choice_id"],
        "choice_option": "确认写入",
        "group": 99,
        "user_message": "确认写入",
        AUTHORING_EXTRA_KEY: authoring_context(_user(), "skill_test"),
    }
    params.update(overrides)
    return params


def test_explicit_request_ignores_assistant_and_prompt():
    assert user_requested_skill_package("请把这个做成技能包") is True
    assert user_requested_skill_package("你好") is False
    assert user_requested_skill_package("名称叫查磁盘", [{"event": "user", "message": "做成技能"}]) is True
    assert user_requested_skill_package("你好", [{"event": "bot", "message": "要不要做成技能包"}]) is False
    assert user_can_add_skill_package(SimpleNamespace(id=None, username="im", is_authenticated=True)) is False
    assert user_can_add_skill_package(_user(permission={"opspilot": set()})) is False
    assert user_can_add_skill_package(_user(is_superuser=True, permission={})) is True


def test_planner_adds_tool_only_when_user_asked():
    empty = ToolExecutionPlan(goal="hi", steps=[])
    names = {PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL}
    asked = enforce_prepare_conversation_skill_package(empty, names, user_message="请做成技能包")
    assert asked.steps[0].tools == [PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL]
    assert enforce_prepare_conversation_skill_package(empty, names, user_message="你好").steps == []
    prompt_only = enforce_prepare_conversation_skill_package(
        empty,
        names,
        user_message="你好",
        conversation_messages=[SimpleNamespace(type="system", content=AUTHORING_PROMPT_SUFFIX)],
    )
    assert prompt_only.steps == []
    tool = SimpleNamespace(name=PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL)
    assert DeepAgentAssemblyMixin._skill_package_request_needs_planner([tool], "你好") is False
    assert DeepAgentAssemblyMixin._skill_package_request_needs_planner([tool], "做成技能包") is True
    assert DeepAgentAssemblyMixin._business_tool_names([tool]) == []


@pytest.mark.django_db
def test_confirm_creates_enabled_package_without_selecting_it(caplog, monkeypatch):
    skill = _skill()
    SkillPackage.objects.create(
        package_id="already",
        name="查磁盘",
        domain="example.com",
        team=[8],
        skill_markdown="old",
        triggers=["旧"],
    )
    caplog.set_level(logging.INFO, logger="opspilot")
    prepared, _request = _issue(skill)
    assert prepared["ok"] is True
    assert "再增加一条" in prepared["text"]
    pending = peek_pending_question("thread:thread-1")
    draft = pending["skill_package_draft"]
    assert draft["triggers"] == ["磁盘", "空间"]
    assert draft["skill_markdown"] == _BODY

    reply = try_commit_conversation_skill_package(_confirm_params(skill, draft))
    created = SkillPackage.objects.exclude(package_id="already").get()
    skill.refresh_from_db()

    assert "添加技能包" in reply
    assert created.name == "查磁盘"
    assert created.is_enabled is True
    assert created.is_build_in is False
    assert created.source_type == "conversation"
    assert created.version == "0.1.0"
    assert created.storage_path == ""
    assert created.required_tools == []
    assert created.team == [3, 8]
    assert created.package_id != "查磁盘"
    assert created.domain == "example.com"
    assert created.created_by == "alice"
    assert skill.skill_packages == ["keep-me"]
    assert created.skill_markdown == _BODY
    # 测试事务里 close_old_connections 会换一条看不见未提交数据的连接。
    monkeypatch.setattr(
        "apps.opspilot.services.skill_package.runtime.run_with_db_cleanup",
        lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    hydrated = hydrate_skill_packages([{"id": created.id, "name": created.name}])
    assert hydrated[0]["skill_markdown"] == _BODY
    assert "extracted_root" not in hydrated[0]
    rendered = "\n".join(record.getMessage() for record in caplog.records if record.name == "opspilot")
    assert "event=conversation_skill_package_saved" in rendered
    assert "SECRET_BODY_SENTINEL" not in rendered
    assert _BODY not in rendered


@pytest.mark.django_db
def test_skill_session_confirm_uses_saved_team():
    skill = _skill(team=[4])
    authoring = authoring_context(_user(), "web_chat")
    request = SimpleNamespace(
        extra_config={
            "skill_id": skill.id,
            "skill_session_id": "sess-1",
            "conversation_key": "skill:sess-1",
            AUTHORING_EXTRA_KEY: authoring,
        },
        user_message="保存成技能包",
        chat_history=[],
        thread_id="",
    )
    config = {"configurable": {"skill_session_id": "sess-1", "graph_request": request, "node_id": "skill_channel"}}
    prepared = prepare_conversation_skill_package(
        name="巡检",
        description="每天巡检时使用",
        triggers=["巡检"],
        skill_markdown=_BODY,
        graph_request=request,
        config=config,
    )
    publish_conversation_skill_package_choice(prepared, graph_request=request, config=config, messages=[], tool_call_id="call-1")
    draft = peek_pending_question("skill:sess-1")["skill_package_draft"]
    reply = try_commit_conversation_skill_package(
        {
            "skill_session_id": "sess-1",
            "group": 99,
            "choice_id": draft["choice_id"],
            "choice_option": "确认写入",
            AUTHORING_EXTRA_KEY: authoring,
        }
    )
    created = SkillPackage.objects.get()
    assert "巡检" in reply
    assert created.team == [4]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("description", "  "),
        ("triggers", []),
        ("skill_markdown", ""),
    ],
)
def test_missing_field_does_not_issue_card(field, value):
    skill = _skill()
    prepared, _request = _issue(skill, **{field: value})
    assert prepared["ok"] is False
    assert "还缺" in prepared["text"]
    assert peek_pending_question("thread:thread-1") is None
    assert SkillPackage.objects.count() == 0


@pytest.mark.django_db
def test_no_permission_disabled_entry_and_empty_team_do_not_issue_card():
    skill = _skill()
    denied, _request = _issue(skill, authoring=authoring_context(_user(permission={"opspilot": set()}), "skill_test"))
    assert denied["ok"] is False
    assert "新增权限" in denied["text"]

    blocked, _request = _issue(skill, authoring=authoring_context(_user(), "embedded_chat"))
    assert blocked["ok"] is False
    assert "当前入口" in blocked["text"]

    ungrouped = _skill(name="empty-team", team=[])
    missing_team, _request = _issue(ungrouped, thread_id="thread-empty")
    assert missing_team["ok"] is False
    assert "管理分组" in missing_team["text"]
    assert peek_pending_question("thread:thread-1") is None
    assert SkillPackage.objects.count() == 0


@pytest.mark.django_db
def test_abandon_typed_text_expired_and_repeat_do_not_insert():
    skill = _skill()
    prepared, _request = _issue(skill)
    draft = peek_pending_question("thread:thread-1")["skill_package_draft"]
    abandoned = try_commit_conversation_skill_package(_confirm_params(skill, draft, choice_option="放弃"))
    assert abandoned.startswith("已放弃")
    assert SkillPackage.objects.count() == 0

    prepared, _request = _issue(skill, thread_id="thread-typed")
    draft = peek_pending_question("thread:thread-typed")["skill_package_draft"]
    typed = try_commit_conversation_skill_package(
        _confirm_params(skill, draft, thread_id="thread-typed", choice_id="", choice_option="", user_message="确认写入")
    )
    assert typed is None
    assert peek_pending_question("thread:thread-typed") is None
    assert SkillPackage.objects.count() == 0

    prepared, _request = _issue(skill, thread_id="thread-expire")
    draft = peek_pending_question("thread:thread-expire")["skill_package_draft"]
    cache_key = f"{PENDING_QUESTION_PREFIX}:thread:thread-expire"
    payload = cache.get(cache_key)
    payload["created_at"] = int(time.time() * 1000) - (PENDING_QUESTION_TTL_SECONDS + 5) * 1000
    cache.set(cache_key, payload, 3600)
    expired = try_commit_conversation_skill_package(_confirm_params(skill, draft, thread_id="thread-expire"))
    assert "失效" in expired
    assert SkillPackage.objects.count() == 0

    prepared, _request = _issue(skill, thread_id="thread-repeat")
    draft = peek_pending_question("thread:thread-repeat")["skill_package_draft"]
    params = _confirm_params(skill, draft, thread_id="thread-repeat", **{AUTHORING_EXTRA_KEY: authoring_context(_user(), "platform")})
    assert "添加技能包" in try_commit_conversation_skill_package(params)
    again = try_commit_conversation_skill_package(params)
    assert "失效" in again
    assert SkillPackage.objects.count() == 1


@pytest.mark.django_db
def test_confirm_rechecks_permission_and_entry():
    skill = _skill()
    _prepared, _request = _issue(skill)
    draft = peek_pending_question("thread:thread-1")["skill_package_draft"]
    denied = try_commit_conversation_skill_package(
        _confirm_params(skill, draft, **{AUTHORING_EXTRA_KEY: authoring_context(_user(permission={"opspilot": set()}), "skill_test")})
    )
    assert "新增权限" in denied
    assert SkillPackage.objects.count() == 0

    _prepared, _request = _issue(skill)
    draft = peek_pending_question("thread:thread-1")["skill_package_draft"]
    blocked = try_commit_conversation_skill_package(
        _confirm_params(skill, draft, **{AUTHORING_EXTRA_KEY: authoring_context(_user(), "feishu")})
    )
    assert "当前入口" in blocked
    assert SkillPackage.objects.count() == 0


@pytest.mark.django_db
def test_create_failure_restores_pending_card(caplog, monkeypatch):
    skill = _skill()
    _prepared, _request = _issue(skill)
    pending = peek_pending_question("thread:thread-1")
    draft = pending["skill_package_draft"]
    created_at = pending["created_at"]
    params = _confirm_params(skill, draft)
    real_create = SkillPackage.objects.create
    boom = RuntimeError("db down")

    def _fail_once(*args, **kwargs):
        if _fail_once.calls == 0:
            _fail_once.calls += 1
            raise boom
        return real_create(*args, **kwargs)

    _fail_once.calls = 0
    monkeypatch.setattr(SkillPackage.objects, "create", _fail_once)
    caplog.set_level(logging.INFO, logger="opspilot")

    with pytest.raises(RuntimeError) as caught:
        try_commit_conversation_skill_package(params)

    restored = peek_pending_question("thread:thread-1")
    assert caught.value is boom
    assert SkillPackage.objects.count() == 0
    assert restored["created_at"] == created_at
    assert restored["kind"] == pending["kind"]
    assert restored["skill_package_draft"]["choice_id"] == draft["choice_id"]
    assert restored["skill_package_draft"]["name"] == draft["name"]
    assert restored["skill_package_draft"]["skill_markdown"] == draft["skill_markdown"]
    rendered = "\n".join(record.getMessage() for record in caplog.records if record.name == "opspilot")
    assert "SECRET_BODY_SENTINEL" not in rendered
    assert _BODY not in rendered

    reply = try_commit_conversation_skill_package(params)
    created = SkillPackage.objects.get()
    assert "添加技能包" in reply
    assert created.name == "查磁盘"
    assert created.skill_markdown == _BODY
    assert peek_pending_question("thread:thread-1") is None


@pytest.mark.django_db
def test_middleware_ends_turn_only_when_draft_is_complete():
    skill = _skill()
    authoring = authoring_context(_user(), "skill_test")
    request = _request(skill, "生成技能包", authoring)

    def _state(**fields):
        args = {
            "name": "查磁盘",
            "description": "磁盘快满时使用",
            "triggers": ["磁盘"],
            "skill_markdown": _BODY,
        }
        args.update(fields)
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-pkg",
                            "name": PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
                            "args": args,
                        }
                    ],
                )
            ]
        }

    class _Runtime:
        def __init__(self, configurable):
            self.config = {"configurable": configurable}

    middleware = ConversationSkillPackageMiddleware()
    result = middleware.after_model(_state(), _Runtime(_config(request)["configurable"]))
    assert result["jump_to"] == "end"
    assert "SECRET_BODY_SENTINEL" in result["messages"][1].content
    assert "SECRET_BODY_SENTINEL" not in result["messages"][0].content
    assert peek_pending_question("thread:thread-1")["skill_package_draft"]["name"] == "查磁盘"

    denied_request = _request(skill, "生成技能包", authoring_context(_user(permission={"opspilot": set()}), "skill_test"), thread_id="thread-denied")
    assert middleware.after_model(_state(), _Runtime(_config(denied_request)["configurable"])) is None


def test_confirm_stream_does_not_load_model(monkeypatch):
    seen = {}

    def _commit(params):
        seen["params"] = params
        return "已写入技能包「查磁盘」。请刷新智能体配置页，在「添加技能包」里勾选。"

    def _prepare(_params):
        raise AssertionError("should not load model")

    monkeypatch.setattr(agui_chat, "try_commit_conversation_skill_package", _commit)
    monkeypatch.setattr(agui_chat, "_prepare_agui_chat_kwargs", _prepare)

    async def _collect():
        lines = []
        async for line in agui_chat._generate_agui_stream(
            {"thread_id": "thread-stream", "choice_id": "abc", "choice_option": "确认写入"},
            "skill",
            "basic",
            False,
            {"content": []},
            {},
            "127.0.0.1",
            "确认写入",
            1,
            None,
        ):
            lines.append(line)
        return lines

    lines = asyncio.run(_collect())
    text = "".join(lines)
    assert seen["params"]["choice_id"] == "abc"
    assert "TEXT_MESSAGE_CONTENT" in text
    assert "添加技能包" in text
    assert text.count("TEXT_MESSAGE_START") == 1
