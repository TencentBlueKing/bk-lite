"""对话把明确要求记下的知识落成文本资料。"""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory

from apps.base.models import User as AuthUser
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader
from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, LLMSkill, Material, PageVersion, WikiKnowledgeBase
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY
from apps.opspilot.services.wiki.chat_material_service import (
    REPLY_DENIED,
    REPLY_FAILED,
    REPLY_KB_DENIED,
    REPLY_NAME_KB,
    REPLY_NO_KB,
    REPLY_NOT_WRITTEN,
    REPLY_SUCCESS,
    REPLY_SWITCH_OFF,
    SAVE_WIKI_MATERIAL_TOOL_NAME,
    SUMMARY_CONFIRMED,
    SUMMARY_CONFLICT,
    SUMMARY_GENERATED_PREFIX,
    SUMMARY_QUIET,
    WIKI_MATERIAL_ACTOR_KEY,
    WIKI_MATERIAL_TOOL_NAME,
    actor_for_chat_flow_input,
    apply_wiki_material_runtime,
    external_actor,
    is_chat_sourced_material,
    read_chat_wiki_outcome,
    system_actor,
    wiki_grounded_uses_single_model_call,
    write_chat_wiki_material,
)
from apps.opspilot.services.wiki.check_service import create_candidate
from apps.opspilot.services.wiki.material_build_queue_service import QUEUE_ITEM_TRIGGER
from apps.opspilot.services.wiki.material_source_service import source_metadata
from apps.opspilot.tests.wiki.factories import WikiFactory
from apps.opspilot.views.chat_wiki_material import chat_wiki_material_decide, chat_wiki_material_outcome
from apps.system_mgmt.models import User as SystemUser
from apps.system_mgmt.models.operation_log import OperationLog

pytestmark = pytest.mark.django_db

_BODY_TAIL = "BODY_TAIL_SENTINEL"
_BROKER_SECRET = "redis://:hunter2-secret@broker:6379/0"


def _user(username="alice", domain="corp.example", user_id="user-alice", disabled=False, group_list=None):
    return SystemUser.objects.create(
        username=username,
        domain=domain,
        display_name=username[:100],
        email=f"{username[:40]}@example.com",
        password="x",
        user_id=user_id,
        disabled=disabled,
        group_list=[{"id": 1, "name": "运维"}] if group_list is None else group_list,
    )


def _skill(*knowledge_bases, allow=True, name="wiki-writer"):
    skill = LLMSkill.objects.create(
        name=name,
        team=[1],
        usage_team=[1],
        allow_wiki_material_write=allow,
    )
    if knowledge_bases:
        skill.wiki_knowledge_bases.add(*knowledge_bases)
    return skill


def _kb(name):
    return WikiFactory().knowledge_base(name=name)


def _patch_runner():
    return patch(
        "apps.opspilot.services.wiki.material_build_queue_service.kick_kb_material_build_runner",
        return_value=True,
    )


def _write(skill, user, **overrides):
    payload = {
        "skill": skill,
        "explicit_request": True,
        "title": "磁盘将满",
        "body": "根分区连续上涨，先清理日志再扩容。",
        "knowledge_base_name": "",
        "actor": system_actor(user.username, user.domain),
    }
    payload.update(overrides)
    return write_chat_wiki_material(**payload)


def test_success_enqueues_text_material_and_records_the_person(caplog):
    user = _user(username="u" * 40, user_id="long-user")
    kb = _kb("运维知识")
    skill = _skill(kb)
    body = ("甲" * 50) + _BODY_TAIL
    caplog.set_level("WARNING", logger="opspilot")

    with _patch_runner():
        reply = _write(skill, user, title="  " + ("标题" * 200), body=body, knowledge_base_name="别的库")

    assert reply == REPLY_SUCCESS
    assert reply == "正在写入，请在此等待结果"
    assert "稍候可以在知识库看到新知识" not in reply
    material = Material.objects.get()
    outcome = read_chat_wiki_outcome(material)
    assert set(outcome) == {"material_id", "phase", "summary", "pages", "checks"}
    assert outcome["material_id"] == material.id
    assert outcome["phase"] == "writing"
    assert outcome["summary"] == reply
    assert outcome["pages"] == []
    assert outcome["checks"] == []
    assert material.knowledge_base_id == kb.id
    assert material.material_type == "text"
    assert material.status == "queued"
    assert material.text_content == body
    assert material.name == ("标题" * 200).strip()[:255]
    assert material.created_by == user.username[:32]
    assert len(material.created_by) == 32
    expected_source = source_metadata(kb, source_relative_path=f"chat/{material.id}.txt")
    assert material.source_relative_path == expected_source["source_relative_path"]
    assert material.source_folder_path == expected_source["source_folder_path"]
    assert material.source_identity == expected_source["source_identity"]
    assert material.source_identity
    assert material.chat_sourced is True
    log = OperationLog.objects.get()
    assert log.app == "opspilot"
    assert log.action_type == OperationLog.ACTION_CREATE
    assert log.target_type == "wiki_material"
    assert log.target_id == str(material.id)
    assert log.username == user.username
    assert log.domain == user.domain
    assert log.source_ip == "0.0.0.0"
    assert log.detail == {
        "knowledge_base_id": kb.id,
        "knowledge_base_name": kb.name,
        "material_name": material.name,
        "material_id": material.id,
        "body_excerpt": "甲" * 50,
    }
    assert _BODY_TAIL not in log.detail["body_excerpt"]
    assert KnowledgePage.objects.count() == 0
    assert BuildRecord.objects.filter(trigger=QUEUE_ITEM_TRIGGER, inputs__material_id=material.id).exists()
    assert _BODY_TAIL not in caplog.text
    assert body not in caplog.text


def test_enqueue_error_discards_material_and_does_not_claim_success(caplog):
    user = _user()
    skill = _skill(_kb("运维知识"))
    caplog.set_level("WARNING", logger="opspilot")

    with patch(
        "apps.opspilot.services.wiki.chat_material_service.enqueue_material_builds",
        side_effect=RuntimeError(_BROKER_SECRET),
    ):
        reply = _write(skill, user, body="正文哨兵不应出现在日志")

    assert reply == REPLY_FAILED
    assert REPLY_SUCCESS not in reply
    assert Material.objects.count() == 0
    assert OperationLog.objects.count() == 0
    assert _BROKER_SECRET not in caplog.text
    assert "正文哨兵不应出现在日志" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


def test_enqueue_without_queue_id_discards_material():
    user = _user()
    skill = _skill(_kb("运维知识"))

    with patch(
        "apps.opspilot.services.wiki.chat_material_service.enqueue_material_builds",
        return_value={"queued": [], "already_queued": [], "skipped": [{"id": 1, "reason": "invalid"}]},
    ):
        reply = _write(skill, user)

    assert reply == REPLY_FAILED
    assert Material.objects.count() == 0
    assert OperationLog.objects.count() == 0


def test_audit_failure_after_enqueue_keeps_queued_material(caplog):
    user = _user()
    kb = _kb("运维知识")
    skill = _skill(kb)
    body = "根分区连续上涨，先清理日志再扩容。"
    caplog.set_level("WARNING", logger="opspilot")

    with _patch_runner(), patch(
        "apps.opspilot.services.wiki.chat_material_service.OperationLog.objects.create",
        side_effect=RuntimeError("audit down"),
    ):
        reply = _write(skill, user, body=body)

    assert reply == REPLY_SUCCESS
    material = Material.objects.get()
    assert material.status == "queued"
    assert material.text_content == body
    assert OperationLog.objects.count() == 0
    assert BuildRecord.objects.filter(trigger=QUEUE_ITEM_TRIGGER, inputs__material_id=material.id).exists()
    records = [record for record in caplog.records if record.name == "opspilot" and record.levelname == "WARNING"]
    audit = [record for record in records if record.msg == "chat wiki material audit failed kb_id=%s material_id=%s error_type=%s"]
    event = [record for record in records if record.msg == "chat wiki material event failed material_id=%s error_type=%s"]
    assert len(audit) == 1
    assert len(event) == 1
    assert audit[0].args == (kb.id, material.id, "RuntimeError")
    rendered = audit[0].getMessage()
    assert rendered == f"chat wiki material audit failed kb_id={kb.id} material_id={material.id} error_type=RuntimeError"
    assert body not in rendered
    assert body not in event[0].getMessage()
    assert "audit down" not in rendered
    assert "Traceback" not in caplog.text


def test_audit_failure_after_build_started_still_reports_success():
    user = _user()
    skill = _skill(_kb("运维知识"))

    def _promote_then_fail(**_kwargs):
        Material.objects.update(status="building")
        raise RuntimeError("audit down")

    with _patch_runner(), patch(
        "apps.opspilot.services.wiki.chat_material_service.OperationLog.objects.create",
        side_effect=_promote_then_fail,
    ):
        reply = _write(skill, user)

    assert reply == REPLY_SUCCESS
    material = Material.objects.get()
    assert material.status == "building"
    assert OperationLog.objects.count() == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"explicit_request": False},
        {"explicit_request": "true"},
        {"title": "  "},
        {"body": ""},
    ],
)
def test_missing_explicit_request_or_text_creates_nothing(overrides):
    user = _user()
    skill = _skill(_kb("运维知识"))

    reply = _write(skill, user, **overrides)

    assert reply == REPLY_NOT_WRITTEN
    assert Material.objects.count() == 0


def test_switch_off_refuses_without_a_material():
    user = _user()
    skill = _skill(_kb("运维知识"), allow=False)

    reply = _write(skill, user)

    assert reply == REPLY_SWITCH_OFF
    assert Material.objects.count() == 0


def test_enabled_skill_without_knowledge_base_refuses():
    user = _user()
    skill = _skill()

    reply = _write(skill, user)

    assert reply == REPLY_NO_KB
    assert Material.objects.count() == 0


def test_single_bound_knowledge_base_ignores_a_wrong_name():
    user = _user()
    bound = _kb("唯一库")
    unbound = _kb("未绑定库")
    skill = _skill(bound)

    with _patch_runner():
        reply = _write(skill, user, knowledge_base_name=unbound.name)

    assert reply == REPLY_SUCCESS
    assert Material.objects.get().knowledge_base_id == bound.id
    assert Material.objects.filter(knowledge_base=unbound).count() == 0


def test_multiple_knowledge_bases_require_one_exact_name():
    user = _user()
    first = _kb(" 磁盘告警 ")
    second = _kb("网络告警")
    unbound = _kb("未绑定库")
    skill = _skill(first, second)

    missing = _write(skill, user, knowledge_base_name="")
    wrong = _write(skill, user, knowledge_base_name=unbound.name)
    assert missing == REPLY_NAME_KB
    assert wrong == REPLY_NAME_KB
    assert Material.objects.count() == 0

    with _patch_runner():
        reply = _write(skill, user, knowledge_base_name="磁盘告警")

    assert reply == REPLY_SUCCESS
    assert Material.objects.get().knowledge_base_id == first.id


def test_duplicate_bound_names_are_refused():
    user = _user()
    skill = _skill(_kb("磁盘告警"), _kb("磁盘告警"))

    reply = _write(skill, user, knowledge_base_name="磁盘告警")

    assert reply == REPLY_NAME_KB
    assert Material.objects.count() == 0


@pytest.mark.parametrize(
    "actor",
    [
        None,
        system_actor("alice", "corp.example"),
        external_actor(""),
        external_actor("om_not_a_person"),
        external_actor("alice@example.com"),
        external_actor("爱丽丝"),
    ],
)
def test_unresolved_person_is_denied(actor):
    user = _user(disabled=actor == system_actor("alice", "corp.example"))
    if actor == external_actor("alice@example.com"):
        user.email = "alice@example.com"
        user.save(update_fields=["email"])
    skill = _skill(_kb("运维知识"))

    reply = _write(skill, user, actor=actor)

    assert reply == REPLY_DENIED
    assert Material.objects.count() == 0


def test_external_sender_matches_one_username_or_user_id():
    by_name = _user(username="ou_real", user_id="id-name", domain="a.example")
    skill = _skill(_kb("运维知识"))
    with _patch_runner():
        reply = _write(skill, by_name, actor=external_actor("ou_real"))
    assert reply == REPLY_SUCCESS
    assert OperationLog.objects.get().username == "ou_real"

    Material.objects.all().delete()
    OperationLog.objects.all().delete()
    by_id = _user(username="bob", user_id="staff-9", domain="b.example")
    with _patch_runner():
        reply = _write(skill, by_id, actor=external_actor("staff-9"))
    assert reply == REPLY_SUCCESS
    assert OperationLog.objects.get().username == "bob"


def test_ambiguous_external_sender_is_denied():
    _user(username="same", user_id="id-a", domain="a.example")
    _user(username="same", user_id="id-b", domain="b.example")
    skill = _skill(_kb("运维知识"))

    reply = _write(skill, SystemUser.objects.first(), actor=external_actor("same"))

    assert reply == REPLY_DENIED
    assert Material.objects.count() == 0

    _user(username="left", user_id="shared-token", domain="c.example")
    _user(username="shared-token", user_id="right-id", domain="d.example")
    reply = _write(skill, SystemUser.objects.first(), actor=external_actor("shared-token"))
    assert reply == REPLY_DENIED
    assert Material.objects.count() == 0


def test_runtime_prompt_and_tool_follow_the_switch():
    off = _skill(allow=False, name="off")
    on = _skill(_kb("运维知识"), allow=True, name="on")
    no_kb = _skill(allow=True, name="no-kb")
    kwargs = {
        "skill_id": off.id,
        WIKI_MATERIAL_ACTOR_KEY: external_actor(""),
    }
    chat_kwargs = {
        "system_message_prompt": "base",
        "tools_servers": [],
        "extra_config": {WIKI_MATERIAL_ACTOR_KEY: system_actor("forged", "evil.example")},
    }

    apply_wiki_material_runtime(chat_kwargs, kwargs)

    assert REPLY_SWITCH_OFF in chat_kwargs["system_message_prompt"]
    assert WIKI_MATERIAL_TOOL_NAME not in [tool.get("name") for tool in chat_kwargs["tools_servers"]]
    assert chat_kwargs["extra_config"][WIKI_MATERIAL_ACTOR_KEY] == external_actor("")

    kwargs["skill_id"] = on.id
    kwargs[WIKI_MATERIAL_ACTOR_KEY] = system_actor("alice", "corp.example")
    apply_wiki_material_runtime(chat_kwargs, kwargs)

    assert "save_wiki_material" in chat_kwargs["system_message_prompt"]
    assert any(tool.get("name") == WIKI_MATERIAL_TOOL_NAME for tool in chat_kwargs["tools_servers"])
    assert chat_kwargs["extra_config"][WIKI_MATERIAL_ACTOR_KEY] == system_actor("alice", "corp.example")
    assert chat_kwargs["extra_config"]["skill_id"] == on.id

    kwargs["skill_id"] = no_kb.id
    apply_wiki_material_runtime(chat_kwargs, kwargs)

    assert REPLY_NO_KB in chat_kwargs["system_message_prompt"]
    assert not any(tool.get("name") == WIKI_MATERIAL_TOOL_NAME for tool in chat_kwargs["tools_servers"])


def test_grounded_answer_keeps_a_tool_turn_when_write_is_enabled():
    assert wiki_grounded_uses_single_model_call(force_wiki_grounded=True, allow_wiki_material_write=False) is True
    assert wiki_grounded_uses_single_model_call(force_wiki_grounded=True, allow_wiki_material_write=True) is False
    assert wiki_grounded_uses_single_model_call(force_wiki_grounded=False, allow_wiki_material_write=True) is False


def test_format_chat_kwargs_injects_write_tool_and_keeps_model_calls(monkeypatch):
    from apps.opspilot.services import chat_service

    skill = _skill(_kb("运维知识"), allow=True, name="format-on")
    monkeypatch.setattr(
        chat_service,
        "augment_prompt_with_trace",
        lambda *_args, **_kwargs: ("augmented", [], {"llm_budget": {"used_calls": 0}}),
    )
    monkeypatch.setattr(
        chat_service,
        "load_wiki_budget_config",
        lambda: SimpleNamespace(qa_max_llm_calls=3, qa_max_output_tokens=1024),
    )
    request = {
        "user_message": "请把这条记到知识库",
        "chat_history": [],
        "conversation_window_size": 10,
        "skill_prompt": "你是运维助手",
        "skill_params": [],
        "wiki_kb_ids": [1],
        "force_wiki_grounded": True,
        "temperature": 1,
        "user_id": "u1",
        "skill_type": SkillTypeChoices.KNOWLEDGE_TOOL,
        "skill_id": skill.id,
        WIKI_MATERIAL_ACTOR_KEY: external_actor("forged"),
    }
    model = SimpleNamespace(
        openai_api_base="http://llm",
        openai_api_key="key",
        model_name="model",
        protocol_type="openai",
        vendor_id=None,
        pk=1,
    )

    chat_kwargs, _, _ = chat_service.ChatService.format_chat_server_kwargs(request, model)

    assert "save_wiki_material" in chat_kwargs["system_message_prompt"]
    assert any(tool.get("name") == WIKI_MATERIAL_TOOL_NAME for tool in chat_kwargs["tools_servers"])
    assert chat_kwargs["extra_config"][WIKI_MATERIAL_ACTOR_KEY] == external_actor("forged")
    assert chat_kwargs.get("max_model_calls") != 1

    skill.allow_wiki_material_write = False
    skill.save(update_fields=["allow_wiki_material_write"])
    closed, _, _ = chat_service.ChatService.format_chat_server_kwargs(request, model)
    assert REPLY_SWITCH_OFF in closed["system_message_prompt"]
    assert closed["max_model_calls"] == 1
    assert not any(tool.get("name") == WIKI_MATERIAL_TOOL_NAME for tool in closed.get("tools_servers") or [])


def test_tool_reads_server_actor_and_has_no_user_argument():
    from apps.opspilot.metis.llm.tools.wiki_material.save import save_wiki_material

    user = _user()
    kb = _kb("运维知识")
    skill = _skill(kb)
    assert "username" not in save_wiki_material.args
    assert WIKI_MATERIAL_ACTOR_KEY not in save_wiki_material.args
    assert "不要声称知识页已经存在" in (save_wiki_material.description or "")
    captured = []

    def _capture(name, payload):
        captured.append((name, payload))

    with _patch_runner(), patch("langchain_core.callbacks.dispatch_custom_event", side_effect=_capture):
        reply = save_wiki_material.func(
            explicit_request=True,
            title="磁盘将满",
            body="根分区连续上涨。",
            knowledge_base_name="",
            config={
                "configurable": {
                    "skill_id": skill.id,
                    "skill_session_id": "sess-wiki-1",
                    WIKI_MATERIAL_ACTOR_KEY: system_actor(user.username, user.domain),
                }
            },
        )

    assert reply == REPLY_SUCCESS
    material = Material.objects.get()
    assert material.knowledge_base_id == kb.id
    assert captured == [
        (
            "wiki_material_write",
            {"material_id": material.id, "phase": "writing", "summary": reply},
        )
    ]
    assert material.text_content not in str(captured)
    assert OperationLog.objects.get().username == user.username


def test_channel_params_keep_server_actor():
    from apps.opspilot.services.skill_channel_chat_service import build_skill_chat_params

    skill = _skill()
    forged = {WIKI_MATERIAL_ACTOR_KEY: system_actor("forged", "evil.example"), "foo": 1}
    external = build_skill_chat_params(
        skill,
        "hi",
        SimpleNamespace(username="im-user", id=None, locale="en"),
        extra=forged,
        wiki_sender_id="ou_real",
    )
    assert external[WIKI_MATERIAL_ACTOR_KEY] == external_actor("ou_real")
    assert external["foo"] == 1

    platform = build_skill_chat_params(
        skill,
        "hi",
        SimpleNamespace(username="alice", domain="corp.example", id=3, locale="zh-CN"),
    )
    assert platform[WIKI_MATERIAL_ACTOR_KEY] == system_actor("alice", "corp.example")

    anonymous = build_skill_chat_params(
        skill,
        "hi",
        SimpleNamespace(username="", id=None, locale="en"),
        wiki_sender_id="",
    )
    assert anonymous[WIKI_MATERIAL_ACTOR_KEY]["mode"] == "external"
    assert anonymous[WIKI_MATERIAL_ACTOR_KEY]["sender_id"] == ""


def test_agent_node_actor_comes_from_caller_identity_only():
    from apps.opspilot.utils.chat_flow_utils.nodes.agent.agent import AgentNode

    class _M2M:
        def values_list(self, *_args, **_kwargs):
            return iter(())

    skill = SimpleNamespace(
        id=9,
        skill_prompt="你是助手",
        skill_params=[],
        skill_packages=[],
        skill_package_params={},
        llm_model_id=1,
        tools=[],
        skill_type="basic",
        team=[1],
        conversation_window_size=10,
        wiki_knowledge_bases=_M2M(),
    )
    node = AgentNode.__new__(AgentNode)
    node.variable_manager = SimpleNamespace(get_variable=lambda *_args, **_kwargs: "")
    params = node._build_llm_params(
        skill,
        "hi",
        {
            "user_id": "u1",
            CALLER_IDENTITY_CONFIG_KEY: {"username": "alice", "domain": "corp.example", "team_id": 1},
            WIKI_MATERIAL_ACTOR_KEY: system_actor("forged", "evil.example"),
        },
    )

    assert params[WIKI_MATERIAL_ACTOR_KEY] == system_actor("alice", "corp.example")

    missing = node._build_llm_params(skill, "hi", {"user_id": "u1"})
    assert missing[WIKI_MATERIAL_ACTOR_KEY]["mode"] == "anonymous"

    forged_channel = node._build_llm_params(
        skill,
        "hi",
        {
            "user_id": "staff-1",
            "channel": "ding_talk",
            WIKI_MATERIAL_ACTOR_KEY: system_actor("forged", "evil.example"),
        },
    )
    assert forged_channel[WIKI_MATERIAL_ACTOR_KEY] == external_actor("staff-1")

    dingtalk = node._build_llm_params(
        skill,
        "hi",
        {
            "user_id": "ignored",
            "channel": "ding_talk",
            WIKI_MATERIAL_ACTOR_KEY: external_actor("staff-9"),
        },
    )
    assert dingtalk[WIKI_MATERIAL_ACTOR_KEY] == external_actor("staff-9")

    wechat = node._build_llm_params(
        skill,
        "hi",
        {"user_id": "zhangsan", "channel": "enterprise_wechat"},
    )
    assert wechat[WIKI_MATERIAL_ACTOR_KEY] == external_actor("zhangsan")

    smuggled = node._build_llm_params(
        skill,
        "hi",
        {"user_id": "staff-9", WIKI_MATERIAL_ACTOR_KEY: external_actor("staff-9")},
    )
    assert smuggled[WIKI_MATERIAL_ACTOR_KEY]["mode"] == "anonymous"
    assert actor_for_chat_flow_input({"channel": "nats", "is_third_party": True, "user_id": "staff-9"})["mode"] == "anonymous"


def test_wechat_chatflow_injects_sender_as_external_actor():
    from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils

    seen = {}

    class _Engine:
        def execute(self, data):
            seen["data"] = data
            return {"content": "ok"}

    with patch("apps.opspilot.utils.base_chat_flow_utils.create_chat_flow_engine", return_value=_Engine()):
        reply = WechatChatFlowUtils(3).execute_chatflow_with_message(SimpleNamespace(), "node-1", "记下这条", "zhangsan")

    assert reply == "ok"
    assert seen["data"]["channel"] == "enterprise_wechat"
    assert seen["data"][WIKI_MATERIAL_ACTOR_KEY] == external_actor("zhangsan")


def test_runtime_strips_wiki_material_tool_by_url_or_category():
    skill = _skill(_kb("运维知识"))
    chat_kwargs = {
        "system_message_prompt": "base",
        "tools_servers": [
            {"name": "renamed", "url": "langchain:wiki_material"},
            {"name": "bundled", "url": "https://example", "category": "prefix langchain:wiki_material"},
            {"name": "listed", "url": "https://example", "category": ["docs", "langchain:wiki_material"]},
            {"name": "keep", "url": "https://example", "category": "search"},
        ],
    }

    apply_wiki_material_runtime(
        chat_kwargs,
        {"skill_id": skill.id, WIKI_MATERIAL_ACTOR_KEY: system_actor("alice", "corp.example")},
    )

    assert [tool.get("name") for tool in chat_kwargs["tools_servers"]] == ["keep", WIKI_MATERIAL_TOOL_NAME]


def test_wiki_material_stays_runtime_loadable_and_cannot_be_saved_as_a_choice():
    loaded = ToolsLoader._discover_specific_tool("wiki_material")
    assert any(item["func"].name == SAVE_WIKI_MATERIAL_TOOL_NAME for item in loaded)
    kept = ToolsLoader.omit_catalog_hidden_skill_tools(
        [
            {"id": 1, "name": "wiki_material"},
            {"id": 2, "name": "shell"},
        ]
    )
    assert kept == [{"id": 2, "name": "shell"}]


def test_chat_conflict_scope_follows_server_mark_not_path():
    assert is_chat_sourced_material(SimpleNamespace(source_relative_path="chat/12.txt", chat_sourced=False)) is False
    assert is_chat_sourced_material(SimpleNamespace(source_relative_path="uploads/note.txt", chat_sourced=True)) is True
    assert is_chat_sourced_material(SimpleNamespace(source_relative_path="chat/12.txt")) is False
    assert is_chat_sourced_material(SimpleNamespace()) is False


def test_upload_paths_and_forged_mark_do_not_relax_conflict_scope(api_client, authenticated_user):
    authenticated_user.permission = {"opspilot": {"wiki_list-View", "wiki_list-Add", "wiki_list-Edit", "wiki_list-Delete"}}
    knowledge_base = WikiKnowledgeBase.objects.create(name="上传库", team=[1])
    created = api_client.post(
        "/api/v1/opspilot/wiki_mgmt/material/",
        {
            "knowledge_base": knowledge_base.id,
            "name": "笔记",
            "material_type": "text",
            "text_content": "客户端指定的正文",
            "source_relative_path": "chat/笔记.txt",
            "chat_sourced": True,
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    assert "chat_sourced" not in created.json()["data"]
    material = Material.objects.get(pk=created.json()["data"]["id"])
    assert material.source_relative_path == "chat/笔记.txt"
    assert material.chat_sourced is False
    assert is_chat_sourced_material(material) is False

    updated = api_client.put(
        f"/api/v1/opspilot/wiki_mgmt/material/{material.id}/",
        {
            "name": "笔记",
            "text_content": "改过的正文",
            "source_relative_path": f"chat/{material.id}.txt",
            "chat_sourced": True,
        },
        format="json",
    )
    assert updated.status_code == 200, updated.content
    material.refresh_from_db()
    assert material.source_relative_path == "chat/笔记.txt"
    assert material.chat_sourced is False
    assert is_chat_sourced_material(material) is False

    file_field = Material._meta.get_field("file")
    original_storage = file_field.storage
    file_field.storage = InMemoryStorage(base_url="/test-media/")
    try:
        uploaded = api_client.post(
            "/api/v1/opspilot/wiki_mgmt/material/batch_create/",
            {
                "knowledge_base": knowledge_base.id,
                "chat_sourced": "true",
                "source_relative_paths": ["chat/笔记.txt"],
                "files": [SimpleUploadedFile("笔记.txt", b"note", content_type="text/plain")],
            },
            format="multipart",
        )
    finally:
        file_field.storage = original_storage

    assert uploaded.status_code == 201, uploaded.content
    batch_material = Material.objects.get(pk=uploaded.json()["data"]["items"][0]["id"])
    assert batch_material.source_relative_path == "chat/笔记.txt"
    assert batch_material.chat_sourced is False
    assert is_chat_sourced_material(batch_material) is False
    assert "chat_sourced" not in uploaded.json()["data"]["items"][0]


def test_migration_marks_only_server_assigned_chat_paths():
    knowledge_base = WikiKnowledgeBase.objects.create(name="历史库", team=[1])
    chat_material = Material.objects.create(
        knowledge_base=knowledge_base,
        name="对话",
        material_type="text",
        text_content="已写入",
        chat_sourced=False,
    )
    chat_material.source_relative_path = f"chat/{chat_material.pk}.txt"
    chat_material.save(update_fields=["source_relative_path"])
    uploaded = Material.objects.create(
        knowledge_base=knowledge_base,
        name="上传",
        material_type="text",
        text_content="笔记",
        source_relative_path="chat/笔记.txt",
        chat_sourced=False,
    )
    guessed = Material.objects.create(
        knowledge_base=knowledge_base,
        name="猜的",
        material_type="text",
        text_content="别的编号",
        source_relative_path="chat/12.txt",
        chat_sourced=False,
    )

    migration = importlib.import_module("apps.opspilot.migrations.0088_material_chat_sourced")
    migration.mark_server_assigned_chat_materials(apps, None)

    chat_material.refresh_from_db()
    uploaded.refresh_from_db()
    guessed.refresh_from_db()
    assert chat_material.chat_sourced is True
    assert is_chat_sourced_material(chat_material) is True
    assert uploaded.chat_sourced is False
    assert guessed.chat_sourced is False
    assert guessed.source_relative_path == "chat/12.txt"


def test_openai_enrich_uses_the_authenticated_user():
    from apps.opspilot.views.chat_flow import _enrich_openai_params

    user = SimpleNamespace(
        username="alice",
        domain="corp.example",
        group_list=[7],
        is_authenticated=True,
    )
    request = SimpleNamespace(user=user, COOKIES={"current_team": "7"}, api_pass=False)
    params = {WIKI_MATERIAL_ACTOR_KEY: external_actor("forged")}

    _enrich_openai_params(request, user, params)

    assert params[WIKI_MATERIAL_ACTOR_KEY] == system_actor("alice", "corp.example")
    assert params[CALLER_IDENTITY_CONFIG_KEY]["username"] == "alice"


def test_outsider_is_told_to_contact_an_admin_and_leaves_nothing():
    user = _user(group_list=[{"id": 9, "name": "别的组"}])
    skill = _skill(_kb("运维知识"))

    reply = _write(skill, user)

    assert reply == REPLY_KB_DENIED
    assert Material.objects.count() == 0
    assert OperationLog.objects.count() == 0


def test_superuser_can_write_without_team_membership():
    user = _user(username="rooty", user_id="user-rooty", group_list=[])
    auth = AuthUser.objects.create_user(username="rooty", password="x", domain=user.domain, locale="zh-CN")
    auth.is_superuser = True
    auth.save(update_fields=["is_superuser"])
    skill = _skill(_kb("运维知识"))

    with _patch_runner():
        reply = _write(skill, user)

    assert reply == REPLY_SUCCESS
    assert read_chat_wiki_outcome(Material.objects.get())["phase"] == "writing"
    assert Material.objects.count() == 1


def test_event_dispatch_failure_still_reports_writing(caplog):
    user = _user()
    skill = _skill(_kb("运维知识"))
    caplog.set_level("WARNING", logger="opspilot")

    with _patch_runner(), patch(
        "langchain_core.callbacks.dispatch_custom_event",
        side_effect=RuntimeError("event down"),
    ):
        reply = _write(skill, user, body="正文不应出现在事件失败日志")

    assert reply == REPLY_SUCCESS
    material = Material.objects.get()
    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "writing"
    assert outcome["summary"] == reply
    assert material.status == "queued"
    assert "event down" not in caplog.text
    assert "正文不应出现在事件失败日志" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


def _chat_material(kb, body="事实"):
    return Material.objects.create(
        knowledge_base=kb,
        name="对话资料",
        material_type="text",
        text_content=body,
        chat_sourced=True,
        status="building",
    )


def _record_build(material, **overrides):
    status = overrides.pop("status", "success")
    counts = overrides.pop("counts", {"new": 0})
    page_actions = overrides.pop("page_actions", [])
    inputs = {"material_id": material.pk}
    extra_inputs = overrides.pop("inputs", None)
    if isinstance(extra_inputs, dict):
        inputs.update(extra_inputs)
    inputs["material_id"] = material.pk
    return BuildRecord.objects.create(
        knowledge_base=material.knowledge_base,
        trigger=QUEUE_ITEM_TRIGGER,
        status=status,
        stage="done",
        counts=counts,
        page_actions=page_actions,
        inputs=inputs,
    )


@pytest.mark.parametrize("status", ["success", "partial"])
def test_published_build_with_a_new_page_names_that_page(status):
    kb = _kb("运维知识")
    material = _chat_material(kb)
    _record_build(
        material,
        status=status,
        counts={"new": 1},
        page_actions=[{"action": "create", "page_id": 41, "title": "磁盘清理"}],
    )

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "published"
    assert outcome["summary"] == f"{SUMMARY_GENERATED_PREFIX}磁盘清理"
    assert outcome["pages"] == [{"id": 41, "title": "磁盘清理"}]
    assert outcome["checks"] == []


def test_published_title_comes_from_the_build_trace_when_the_record_list_is_empty():
    kb = _kb("运维知识")
    material = _chat_material(kb)
    _record_build(
        material,
        counts={"new": 1},
        page_actions=[],
        inputs={"source_trace": {"page_actions": [{"action": "create", "page_id": 41, "title": "磁盘清理"}]}},
    )

    outcome = read_chat_wiki_outcome(material)
    assert outcome["summary"] == f"{SUMMARY_GENERATED_PREFIX}磁盘清理"
    assert outcome["pages"] == [{"id": 41, "title": "磁盘清理"}]


def test_outcome_uses_the_latest_build_for_the_material():
    kb = _kb("运维知识")
    material = _chat_material(kb)
    _record_build(
        material,
        status="failed",
        counts={"new": 1},
        page_actions=[{"action": "create", "page_id": 1, "title": "旧页"}],
    )
    _record_build(
        material,
        status="success",
        counts={"new": 1},
        page_actions=[{"action": "create", "page_id": 41, "title": "磁盘清理"}],
    )

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "published"
    assert outcome["summary"] == f"{SUMMARY_GENERATED_PREFIX}磁盘清理"
    assert outcome["pages"] == [{"id": 41, "title": "磁盘清理"}]


def test_conflict_card_uses_the_frozen_current_body():
    kb = _kb("运维知识")
    material = _chat_material(kb)
    page = KnowledgePage.objects.create(knowledge_base=kb, title="告警规则", page_type="concept")
    frozen = PageVersion.objects.create(page=page, no=1, body="冻结时的规则", is_current=False, change_type="ai_create")
    live = PageVersion.objects.create(page=page, no=2, body="后来改过的规则", is_current=True, change_type="human_edit")
    page.current_version = live
    page.save(update_fields=["current_version"])
    candidate = PageVersion.objects.create(page=page, no=3, body="新规则", is_current=False, change_type="candidate")
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="cannot_merge",
        status="open",
        related={"pages": [page.id], "materials": [material.id]},
        candidate_version=candidate,
        suggested_actions=["keep_current"],
        decision_context={"locked_current_version_id": frozen.id},
    )
    _record_build(material)

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "needs_decision"
    assert outcome["checks"][0]["current_body"] == "冻结时的规则"
    assert outcome["checks"][0]["incoming_body"] == "新规则"


@pytest.mark.parametrize("status", ["success", "partial"])
def test_published_build_without_a_new_page_says_there_is_no_new_conflict(status):
    kb = _kb("运维知识")
    material = _chat_material(kb)
    _record_build(material, status=status)

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "published"
    assert outcome["summary"] == SUMMARY_QUIET
    assert outcome["pages"] == []


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failed_or_cancelled_build_keeps_the_material(status):
    kb = _kb("运维知识")
    material = _chat_material(kb)
    _record_build(material, status=status, counts={"new": 1})

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "failed"
    assert outcome["summary"] == REPLY_FAILED
    assert Material.objects.filter(pk=material.pk, text_content="事实").exists()


@pytest.mark.parametrize("status", ["build_failed", "parse_failed", "invalid"])
def test_failed_material_status_is_a_failed_card(status):
    material = _chat_material(_kb("运维知识"))
    material.status = status
    material.save(update_fields=["status"])

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "failed"
    assert outcome["summary"] == REPLY_FAILED
    assert outcome["pages"] == []
    assert outcome["checks"] == []


def test_open_check_for_this_material_asks_for_a_decision_in_the_chat():
    kb = _kb("运维知识")
    material = _chat_material(kb)
    other = _chat_material(kb, body="另一份")
    page = WikiFactory().page(knowledge_base=kb, title="告警规则", body="现" * 4001)
    candidate = PageVersion.objects.create(page=page, no=2, body="新" * 4001, change_type="candidate", is_current=False)
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        related={"pages": [page.id], "materials": [material.id]},
        candidate_version=candidate,
        suggested_actions=["keep_current", "edit_accept"],
    )
    CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        related={"pages": [page.id], "materials": [other.id]},
        suggested_actions=["keep_current"],
    )

    _record_build(
        material,
        counts={"new": 1},
        page_actions=[{"action": "create", "page_id": page.id, "title": page.title}],
    )

    outcome = read_chat_wiki_outcome(material)
    assert outcome["phase"] == "needs_decision"
    assert outcome["summary"] == SUMMARY_CONFLICT
    assert outcome["pages"] == []
    assert len(outcome["checks"]) == 1
    check = outcome["checks"][0]
    assert check["page_id"] == page.id
    assert check["page_title"] == "告警规则"
    assert check["current_body"] == "现" * 4000
    assert check["incoming_body"] == "新" * 4000
    assert check["actions"] == ["keep_current", "edit_accept"]
    assert check["status"] == "open"
    assert "现" * 4001 not in check["current_body"]


def test_non_chat_material_has_no_write_result():
    kb = _kb("运维知识")
    material = Material.objects.create(
        knowledge_base=kb,
        name="上传资料",
        material_type="text",
        text_content="上传正文",
        chat_sourced=False,
        status="built",
    )
    _record_build(
        material,
        counts={"new": 1},
        page_actions=[{"action": "new", "page_id": 7, "title": "新页"}],
    )

    viewer = _auth_user("member")
    response = _outcome_request(viewer, material.id)
    assert response.status_code == 404
    assert _body(response)["message"] == "没有这条写入结果"
    missing = _outcome_request(viewer, 0)
    assert missing.status_code == 404
    assert _body(missing)["message"] == "没有这条写入结果"
    assert Material.objects.filter(pk=material.pk).exists()


def _auth_user(username, *, superuser=False, groups=None):
    user = AuthUser.objects.create_user(
        username=username,
        password="x",
        domain="corp.example",
        locale="zh-CN",
        group_list=[{"id": 1, "name": "运维"}] if groups is None else groups,
    )
    if superuser:
        user.is_superuser = True
        user.group_list = []
        user.save(update_fields=["is_superuser", "group_list"])
    return user


def _body(response):
    return json.loads(response.content)


def _outcome_request(user, material_id):
    request = APIRequestFactory().get(f"/opspilot/chat_wiki_material/{material_id}/outcome/")
    request.user = user
    return chat_wiki_material_outcome(request, material_id=material_id)


def _decide_request(user, material_id, payload):
    request = APIRequestFactory().post(
        f"/opspilot/chat_wiki_material/{material_id}/decide/",
        payload,
        format="json",
    )
    request.user = user
    return chat_wiki_material_decide(request, material_id=material_id)


def _decision_fixture():
    kb = _kb("运维知识")
    material = _chat_material(kb, body="待确认正文")
    page = KnowledgePage.objects.create(knowledge_base=kb, title="告警规则", page_type="concept")
    current = PageVersion.objects.create(page=page, no=1, body="当前规则", is_current=True, change_type="ai_create")
    page.current_version = current
    page.save(update_fields=["current_version"])
    check = create_candidate(
        page,
        body="新规则",
        reason="conflict",
        check_type="cannot_merge",
        incoming_material=material,
        related={"pages": [page.id], "materials": [material.id]},
        suggested_actions=["keep_current", "edit_accept"],
    )
    _record_build(material)
    return kb, material, check


def test_outcome_and_decision_follow_the_current_operator():
    _kb_row, material, check = _decision_fixture()
    member = _auth_user("member")
    outsider = _auth_user("outsider", groups=[{"id": 9, "name": "别的组"}])
    superuser = _auth_user("boss", superuser=True)
    secret = "SECRET_BODY_SENTINEL"

    denied = _outcome_request(outsider, material.id)
    assert denied.status_code == 403
    assert _body(denied)["message"] == REPLY_KB_DENIED

    allowed = _outcome_request(member, material.id)
    assert allowed.status_code == 200
    payload = _body(allowed)["data"]
    assert set(payload) == {"material_id", "phase", "summary", "pages", "checks"}
    assert payload["phase"] == "needs_decision"
    assert payload["summary"] == SUMMARY_CONFLICT
    assert payload["checks"][0]["current_body"] == "当前规则"
    assert payload["checks"][0]["incoming_body"] == "新规则"
    assert payload["checks"][0]["actions"] == ["keep_current", "edit_accept"]

    boss = _outcome_request(superuser, material.id)
    assert boss.status_code == 200
    assert _body(boss)["data"]["material_id"] == material.id

    rejected = _decide_request(outsider, material.id, {"check_id": check.id, "action": "keep_current"})
    assert rejected.status_code == 403
    check.refresh_from_db()
    assert check.status == "open"
    assert OperationLog.objects.filter(action_type=OperationLog.ACTION_EXECUTE).count() == 0

    unknown = _decide_request(member, material.id, {"check_id": check.id, "action": "drop", "body": secret})
    assert unknown.status_code == 400
    check.refresh_from_db()
    assert check.status == "open"

    decided = _decide_request(
        member,
        material.id,
        {"check_id": check.id, "action": "keep_current", "body": secret},
    )
    assert decided.status_code == 200
    body = decided.content.decode()
    assert secret not in body
    result = _body(decided)["data"]
    assert result["phase"] == "published"
    assert result["summary"] == SUMMARY_CONFIRMED
    assert result["checks"][0]["status"] != "open"
    check.refresh_from_db()
    assert check.status != "open"
    log = OperationLog.objects.get(action_type=OperationLog.ACTION_EXECUTE)
    assert log.app == "opspilot"
    assert log.target_id == str(check.id)
    assert log.username == member.username
    rendered = str(log.detail) + log.summary
    assert secret not in rendered
    assert "body" not in log.detail

    again = _decide_request(member, material.id, {"check_id": check.id, "action": "keep_current", "body": secret})
    assert again.status_code == 200
    assert _body(again)["data"]["phase"] == "published"
    assert _body(again)["data"]["summary"] == SUMMARY_CONFIRMED
    assert OperationLog.objects.filter(action_type=OperationLog.ACTION_EXECUTE).count() == 1


@pytest.mark.parametrize("action", ["use_new", "edit_accept"])
def test_accepting_actions_pass_the_chat_material(action):
    kb = _kb("运维知识")
    material = _chat_material(kb, body="待确认正文")
    page = KnowledgePage.objects.create(knowledge_base=kb, title="告警规则", page_type="concept")
    current = PageVersion.objects.create(page=page, no=1, body="当前规则", is_current=True, change_type="ai_create")
    page.current_version = current
    page.save(update_fields=["current_version"])
    candidate = PageVersion.objects.create(page=page, no=2, body="新规则", is_current=False, change_type="candidate")
    check = CheckItem.objects.create(
        knowledge_base=kb,
        check_type="conflict",
        status="open",
        related={"pages": [page.id], "materials": [material.id]},
        candidate_version=candidate,
        suggested_actions=["keep_current", "use_new", "edit_accept"],
    )
    member = _auth_user(f"member-{action}")

    with patch("apps.opspilot.services.wiki.check_service.decide_check") as decide:
        kept = _decide_request(member, material.id, {"check_id": check.id, "action": "keep_current"})
        accepted = _decide_request(member, material.id, {"check_id": check.id, "action": action, "body": "改后正文"})

    assert kept.status_code == 200
    assert accepted.status_code == 200
    assert [call.args[1] for call in decide.call_args_list] == ["keep_current", action]
    assert decide.call_args_list[0].kwargs["material"] is None
    assert decide.call_args_list[1].kwargs["material"].pk == material.pk
