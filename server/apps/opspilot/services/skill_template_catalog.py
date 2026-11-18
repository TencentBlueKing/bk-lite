import json
from pathlib import Path

from django.db import transaction

from apps.opspilot.models import LLMSkill

CHATFLOW_DATA_DIR = Path(__file__).resolve().parent.parent / "management" / "chatflow_data"
TEMPLATE_DATA_DIR = CHATFLOW_DATA_DIR.parent / "skill_templates"
TEMPLATE_WORKBENCH_IDS = ("k8s", "pgsql", "web_check")
TEMPLATE_CONFIG_FIELDS = (
    "name",
    "introduction",
    "skill_prompt",
    "skill_type",
    "guide",
    "enable_conversation_history",
    "conversation_window_size",
    "run_model_call_limit",
    "temperature",
    "show_think",
    "enable_suggest",
    "enable_query_rewrite",
    "force_wiki_grounded",
    "allow_wiki_material_write",
    "memory_write_rounds",
)


class SkillTemplateCatalogService:
    """同步可移植的内置模板，不修改已有智能体实例或工作台。"""

    @transaction.atomic
    def sync(self) -> list[LLMSkill]:
        definitions = self._load_definitions()
        templates = []
        for key, definition in definitions.items():
            skill_id = f"builtin:opspilot:{key}"
            template = LLMSkill.objects.filter(is_template=True, is_builtin=True, skill_id=skill_id).first()
            if template is None:
                template = self._legacy_template(definition)
            if template is None:
                template = LLMSkill()
            for field, value in definition.items():
                setattr(template, field, value)
            template.skill_id = skill_id
            template.is_template = template.is_builtin = True
            template.llm_model = None
            template.team = template.usage_team = []
            template.skill_params = template.skill_packages = []
            template.skill_package_params = {}
            template.memory_space = None
            template.save()
            template.wiki_knowledge_bases.clear()
            templates.append(template)
        return templates

    @staticmethod
    def _legacy_template(definition):
        return LLMSkill.objects.filter(
            is_template=True,
            is_builtin=False,
            skill_id__isnull=True,
            team=[],
            llm_model__isnull=True,
            name=definition["name"],
            introduction__in=[definition["introduction"], definition["name"]],
            skill_prompt=definition["skill_prompt"],
            skill_type=definition["skill_type"],
            tools=definition["tools"],
        ).first()

    @staticmethod
    def _workbench_config():
        return json.loads((CHATFLOW_DATA_DIR / "config.json").read_text(encoding="utf-8"))

    def _load_definitions(self) -> dict[str, dict]:
        config = self._workbench_config()
        by_id = {item["id"]: item for item in config}
        definitions = {}
        defaults = {field: LLMSkill._meta.get_field(field).get_default() for field in TEMPLATE_CONFIG_FIELDS}
        for workbench_id in TEMPLATE_WORKBENCH_IDS:
            item = by_id[workbench_id]
            prompt = (CHATFLOW_DATA_DIR / workbench_id / "check.txt").read_text(encoding="utf-8")
            definitions[workbench_id] = {
                **defaults,
                "name": item["name"],
                "skill_prompt": prompt,
                "introduction": item.get("description") or item["name"],
                "skill_type": item["check_skill_type"],
                "tools": [{"name": tool_name, "kwargs": []} for tool_name in item.get("tools", [])],
            }
        assistant = json.loads((TEMPLATE_DATA_DIR / "ai_assistant.json").read_text(encoding="utf-8"))
        definitions["ai_assistant"] = {
            **defaults,
            **{field: assistant[field] for field in TEMPLATE_CONFIG_FIELDS if field in assistant},
            "tools": [{"name": tool["name"], "kwargs": []} for tool in assistant["tools"]],
        }
        return definitions
