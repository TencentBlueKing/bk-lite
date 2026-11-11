"""替换智能体模板命令：只留下两个工作台主智能体的发版定义。"""

import pytest
from django.core.management import call_command

from apps.core.management.commands.batch_init import Command
from apps.opspilot.models import LLMSkill
from apps.opspilot.services.skill_template_catalog import CHATFLOW_DATA_DIR
from apps.opspilot.tests.test_slice_ops_llm_views import _body, _dispatch
from apps.opspilot.viewsets.llm_view import LLMViewSet

pytestmark = pytest.mark.django_db


def _prompt(workbench_id: str) -> str:
    return (CHATFLOW_DATA_DIR / workbench_id / "check.txt").read_text(encoding="utf-8")


def test_init_skill_templates_keeps_only_two_workbench_agents():
    LLMSkill.objects.create(name="Python Genius", is_template=True, skill_prompt="old")
    LLMSkill.objects.create(name="Kubernetes 助手", is_builtin=True, is_template=False, team=[1], skill_prompt="live")
    LLMSkill.objects.create(name="keep-normal", is_template=False, team=[1])

    call_command("init_skill_templates")

    templates = list(LLMSkill.objects.filter(is_template=True).order_by("name"))
    assert [item.name for item in templates] == ["Kubernetes 助手", "Postgres DB 助手"]
    by_name = {item.name: item for item in templates}
    kubernetes = by_name["Kubernetes 助手"]
    postgres = by_name["Postgres DB 助手"]
    assert kubernetes.skill_prompt == _prompt("k8s")
    assert postgres.skill_prompt == _prompt("pgsql")
    assert kubernetes.skill_type == 3
    assert postgres.skill_type == 1
    assert kubernetes.introduction == "Kubernetes 助手"
    assert postgres.introduction == "Postgres DB 助手"
    assert kubernetes.tools == [{"name": "kubernetes", "kwargs": []}]
    assert postgres.tools == [{"name": "postgres", "kwargs": []}]
    assert kubernetes.is_builtin is False
    assert postgres.is_builtin is False
    assert kubernetes.team == []
    assert postgres.team == []
    assert kubernetes.llm_model_id is None
    assert postgres.llm_model_id is None
    assert not any(tool.get("id") for item in templates for tool in item.tools)

    builtin = LLMSkill.objects.get(name="Kubernetes 助手", is_builtin=True)
    assert builtin.is_template is False
    assert builtin.skill_prompt == "live"
    assert LLMSkill.objects.filter(name="keep-normal", is_template=False).exists()
    assert not LLMSkill.objects.filter(name="Web 应用巡检助手", is_template=True).exists()
    listed = sorted(item["name"] for item in _body(_dispatch(LLMViewSet, "get_template_list", "get")))
    assert listed == ["Kubernetes 助手", "Postgres DB 助手"]

    call_command("init_skill_templates")
    assert list(LLMSkill.objects.filter(is_template=True).order_by("name").values_list("name", flat=True)) == [
        "Kubernetes 助手",
        "Postgres DB 助手",
    ]
    assert LLMSkill.objects.filter(is_builtin=True, name="Kubernetes 助手").count() == 1


def test_startup_leaves_existing_templates_untouched(monkeypatch):
    legacy = LLMSkill.objects.create(name="Python Genius", is_template=True, skill_prompt="old")
    monkeypatch.setattr("apps.core.management.commands.batch_init.call_command", lambda *args, **kwargs: None)
    Command()._init_opspilot()
    legacy.refresh_from_db()
    assert legacy.skill_prompt == "old"
    assert list(LLMSkill.objects.filter(is_template=True).values_list("name", flat=True)) == ["Python Genius"]


def test_init_llm_still_restores_legacy_template_catalog():
    call_command("init_skill_templates")
    call_command("init_llm")
    names = set(LLMSkill.objects.filter(is_template=True).values_list("name", flat=True))
    assert "Python Genius" in names
    assert "Kubernetes 助手" not in names
