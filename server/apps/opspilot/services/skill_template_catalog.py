import json
from pathlib import Path

from apps.opspilot.models import LLMSkill

CHATFLOW_DATA_DIR = Path(__file__).resolve().parent.parent / "management" / "chatflow_data"
TEMPLATE_WORKBENCH_IDS = ("k8s", "pgsql")


class SkillTemplateCatalogService:
    """用两个工作台主智能体的发版定义替换全部智能体模板。"""

    def replace(self) -> list[LLMSkill]:
        definitions = self._load_definitions()
        LLMSkill.objects.filter(is_template=True).delete()
        return [LLMSkill.objects.create(**definition, is_template=True, is_builtin=False, team=[]) for definition in definitions]

    def _load_definitions(self) -> list[dict]:
        config_path = CHATFLOW_DATA_DIR / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in config}
        definitions = []
        for workbench_id in TEMPLATE_WORKBENCH_IDS:
            item = by_id[workbench_id]
            prompt = (CHATFLOW_DATA_DIR / workbench_id / "check.txt").read_text(encoding="utf-8")
            definitions.append(
                {
                    "name": item["name"],
                    "skill_prompt": prompt,
                    "introduction": item.get("description") or item["name"],
                    "skill_type": item["check_skill_type"],
                    "tools": [{"name": tool_name, "kwargs": []} for tool_name in item.get("tools", [])],
                }
            )
        return definitions
