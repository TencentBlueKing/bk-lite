"""内置能力仅播种模板；升级不破坏用户实例与引用。"""

import json

import pytest
from django.core.management import call_command

from apps.core.management.commands.batch_init import Command
from apps.opspilot.enum import BotTypeChoice
from apps.opspilot.models import Bot, BotConversationHistory, BotWorkFlow, LLMSkill, SkillChannel, SkillConversation
from apps.opspilot.services.skill_template_catalog import CHATFLOW_DATA_DIR, TEMPLATE_CONFIG_FIELDS, TEMPLATE_DATA_DIR, SkillTemplateCatalogService
from apps.opspilot.tests.test_slice_ops_llm_views import _body, _dispatch
from apps.opspilot.viewsets.llm_view import LLMViewSet

pytestmark = pytest.mark.django_db
EXPECTED_NAMES = {"AI智能助手", "Kubernetes 助手", "Postgres DB 助手", "Web 应用巡检助手"}


def _seed_skill(name):
    return LLMSkill.objects.create(name=name, is_builtin=True, team=[1], created_by="admin", domain="domain.com")


def _seed_bot(name):
    return Bot.objects.create(name=name, is_builtin=True, bot_type=BotTypeChoice.CHAT_FLOW, team=[1], created_by="admin", domain="domain.com")


def test_sync_is_idempotent_and_preserves_user_instances_and_templates():
    custom = LLMSkill.objects.create(name="AI智能助手", team=[1], skill_prompt="my live assistant")
    custom_template = LLMSkill.objects.create(name="Kubernetes 助手", is_template=True, team=[1], skill_prompt="my template")
    call_command("init_skill_templates")
    first_ids = set(LLMSkill.objects.filter(is_template=True, is_builtin=True).values_list("id", flat=True))
    call_command("init_skill_templates")
    templates = list(LLMSkill.objects.filter(is_template=True, is_builtin=True))
    assert {item.name for item in templates} == EXPECTED_NAMES
    assert {item.id for item in templates} == first_ids
    custom.refresh_from_db()
    custom_template.refresh_from_db()
    assert custom.skill_prompt == "my live assistant" and not custom.is_builtin
    assert custom_template.skill_prompt == "my template" and not custom_template.is_builtin
    assert not Bot.objects.exists()
    assert LLMSkill.objects.filter(is_template=False).count() == 1
    for template in templates:
        assert template.skill_id.startswith("builtin:opspilot:")
        assert template.llm_model_id is None and template.memory_space_id is None
        assert template.team == template.usage_team == template.skill_params == template.skill_packages == []
        assert template.skill_package_params == {} and not template.wiki_knowledge_bases.exists()
        assert all(set(tool) == {"name", "kwargs"} and tool["kwargs"] == [] for tool in template.tools)


def test_ai_assistant_preserves_published_portable_configuration():
    call_command("init_skill_templates")
    assistant = LLMSkill.objects.get(skill_id="builtin:opspilot:ai_assistant")
    published = json.loads((TEMPLATE_DATA_DIR / "ai_assistant.json").read_text())
    for field in TEMPLATE_CONFIG_FIELDS:
        assert getattr(assistant, field) == published[field]
    assert assistant.tools == published["tools"]
    assert assistant.run_model_call_limit == 100 and assistant.temperature == 1.0
    assert assistant.guide.endswith("[列出当前活跃告警][CMDB有哪些资产未被监控]")


@pytest.mark.parametrize("key", ["k8s", "pgsql", "web_check"])
@pytest.mark.parametrize("legacy_introduction", [False, True])
def test_adopts_only_matching_legacy_release_templates(key, legacy_introduction):
    definition = SkillTemplateCatalogService()._load_definitions()[key]
    original = {**definition, "introduction": definition["name"]} if legacy_introduction else definition
    old = LLMSkill.objects.create(**original, is_template=True, team=[])
    other = LLMSkill.objects.create(name=old.name, is_template=True, skill_prompt="user authored", team=[])
    custom_description = LLMSkill.objects.create(**{**definition, "introduction": "user authored introduction"}, is_template=True, team=[])
    call_command("init_skill_templates")
    call_command("init_skill_templates")
    old.refresh_from_db()
    other.refresh_from_db()
    custom_description.refresh_from_db()
    assert old.is_builtin and old.skill_id == f"builtin:opspilot:{key}"
    assert old.introduction == definition["introduction"]
    assert LLMSkill.objects.filter(is_builtin=True, is_template=True).count() == 4
    assert not other.is_builtin and other.skill_prompt == "user authored"
    assert not custom_description.is_builtin and custom_description.introduction == "user authored introduction"


@pytest.mark.parametrize("command", ["init_skill_templates", "init_chatflow", "init_llm"])
def test_upgrade_preserves_all_existing_instance_fields(command):
    config = json.loads((CHATFLOW_DATA_DIR / "config.json").read_text())
    for item in config:
        bot = _seed_bot(item["name"])
        bot.introduction = "customer modified workbench"
        bot.save(update_fields=["introduction"])
        _seed_skill(item["format_skill_name"])
        skill = _seed_skill(item["name"])
        skill.skill_prompt = "customer modified prompt"
        skill.tools = [{"name": "shell", "kwargs": [{"name": "customer_option", "value": "preserve me"}]}]
        skill.save(update_fields=["skill_prompt", "tools"])
    LLMSkill.objects.create(name="Postgres DB 助手", team=[1], skill_prompt="mine")
    Bot.objects.create(name="Kubernetes 助手", team=[1])
    foreign_skill = _seed_skill("Postgres DB 助手")
    foreign_skill.domain = "other-domain"
    foreign_skill.save(update_fields=["domain"])
    foreign_bot = _seed_bot("Kubernetes 助手")
    foreign_bot.domain = "other-domain"
    foreign_bot.save(update_fields=["domain"])
    skills_before = list(LLMSkill.objects.filter(is_template=False).order_by("id").values())
    bots_before = list(Bot.objects.order_by("id").values())
    for _ in range(2):
        call_command(command)
        assert list(LLMSkill.objects.filter(is_template=False).order_by("id").values()) == skills_before
        assert list(Bot.objects.order_by("id").values()) == bots_before
        assert LLMSkill.objects.filter(is_template=True, is_builtin=True).count() == 4


@pytest.mark.parametrize("command", ["init_skill_templates", "init_chatflow", "init_llm"])
def test_upgrade_preserves_existing_relations_and_history(command, mocker):
    from apps.workflow.models import Workflow, WorkflowVersion

    linked = _seed_skill("Kubernetes 助手")
    json_linked = _seed_skill("Postgres DB 数据汇总")
    bot = _seed_bot("Postgres DB 助手")
    bot.llm_skills.add(linked)
    mocker.patch("apps.opspilot.models.bot_mgmt.ChatApplication.sync_applications_from_workflow", return_value=(0, 0, 0))
    BotWorkFlow.objects.create(bot=bot, flow_json={"nodes": [{"type": "agents", "data": {"config": {"agent": str(json_linked.id)}}}]})
    workflow = Workflow.objects.create(name="user orchestration", team=[1], definition={"tasks": [{"inputParameters": {"agent_id": linked.id}}]})
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition={"tasks": [{"inputParameters": {"agent_id": linked.id}}]})
    SkillChannel.objects.create(skill=linked, channel_type="web_chat", enabled=True, usage_team=[1])
    SkillConversation.objects.create(skill=linked, session_id="existing-user-conversation")
    BotConversationHistory.objects.create(bot=bot, conversation_role="user", conversation="existing message")
    preserved_models = (Bot, Bot.llm_skills.through, BotWorkFlow, Workflow, WorkflowVersion, SkillChannel, SkillConversation, BotConversationHistory)
    before = {model: list(model.objects.order_by("pk").values()) for model in preserved_models}
    skills_before = list(LLMSkill.objects.filter(is_template=False).order_by("id").values())
    for _ in range(2):
        call_command(command)
        assert list(LLMSkill.objects.filter(is_template=False).order_by("id").values()) == skills_before
        for model, rows in before.items():
            assert list(model.objects.order_by("pk").values()) == rows


def test_catalog_only_exposes_portable_builtin_templates():
    call_command("init_skill_templates")
    LLMSkill.objects.create(name="private template", is_template=True, team=[2], skill_prompt="PRIVATE_SENTINEL")
    body = _body(_dispatch(LLMViewSet, "get_template_list", "get"))
    assert {row["name"] for row in body} == EXPECTED_NAMES
    assert "PRIVATE_SENTINEL" not in json.dumps(body)
    assert all(set(row) == {"id", "tools", *TEMPLATE_CONFIG_FIELDS} for row in body)


def test_catalog_prioritizes_assistant_by_stable_key_independent_of_name():
    call_command("init_skill_templates")
    assistant = LLMSkill.objects.get(skill_id="builtin:opspilot:ai_assistant")
    assistant.name = "renamed assistant"
    assistant.save(update_fields=["name"])
    LLMSkill.objects.filter(skill_id="builtin:opspilot:k8s").update(name="AI智能助手")
    other_ids = list(LLMSkill.objects.filter(is_template=True, is_builtin=True).exclude(pk=assistant.pk).order_by("id").values_list("id", flat=True))
    body = _body(_dispatch(LLMViewSet, "get_template_list", "get"))
    assert [row["id"] for row in body] == [assistant.id, *other_ids]


def test_create_from_template_preserves_behavior_and_leaves_bindings_empty(mocker):
    mocker.patch("apps.opspilot.viewsets.llm_view.log_operation")
    call_command("init_skill_templates")
    templates = _body(_dispatch(LLMViewSet, "get_template_list", "get"))
    template = next(row for row in templates if row["name"] == "AI智能助手")
    payload = {key: value for key, value in template.items() if key != "id"}
    payload["name"] = "created from template"
    response = _dispatch(LLMViewSet, "create", "post", data=payload)
    assert response.status_code == 201
    created = LLMSkill.objects.get(pk=_body(response)["id"])
    assert not created.is_template and not created.is_builtin
    assert created.llm_model_id is None and created.team == [1]
    for field in TEMPLATE_CONFIG_FIELDS:
        assert getattr(created, field) == payload[field]
    assert created.tools == template["tools"]


def test_create_preserves_explicit_history_setting(mocker):
    mocker.patch("apps.opspilot.viewsets.llm_view.log_operation")
    response = _dispatch(LLMViewSet, "create", "post", data={"name": "no history", "enable_conversation_history": False})
    assert response.status_code == 201
    assert not LLMSkill.objects.get(pk=_body(response)["id"]).enable_conversation_history


def test_startup_and_legacy_commands_do_not_create_instances(monkeypatch):
    names = []

    def dispatch(name, *args, **kwargs):
        names.append(name)
        if name == "init_skill_templates":
            call_command(name, *args, **kwargs)

    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", dispatch)
    Command()._init_opspilot()
    assert "init_chatflow" not in names
    for _ in range(2):
        for command in ("init_skill_templates", "init_chatflow", "init_llm"):
            call_command(command)
    assert LLMSkill.objects.filter(is_template=True, is_builtin=True).count() == 4
    assert not LLMSkill.objects.filter(is_template=False).exists()
    assert not Bot.objects.exists()
