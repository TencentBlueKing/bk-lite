"""对话里把明确要求记下或修正的知识写成资料。"""

from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.models import LLMSkill
from apps.opspilot.services.wiki.chat_material_service import (
    REPLY_SWITCH_OFF,
    SAVE_WIKI_MATERIAL_TOOL_NAME,
    WIKI_MATERIAL_ACTOR_KEY,
    write_chat_wiki_material,
)


def _configurable(config: Optional[RunnableConfig]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    configurable = config.get("configurable")
    return configurable if isinstance(configurable, dict) else {}


def _runtime_value(config: Optional[RunnableConfig], key: str):
    configurable = _configurable(config)
    if key in configurable:
        return configurable.get(key)
    request = configurable.get("graph_request")
    extra = getattr(request, "extra_config", None) if request is not None else None
    if isinstance(extra, dict):
        return extra.get(key)
    return None


def _explicit(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return False


@tool(SAVE_WIKI_MATERIAL_TOOL_NAME)
def save_wiki_material(
    explicit_request: bool,
    title: str,
    body: str,
    knowledge_base_name: str = "",
    config: RunnableConfig = None,
) -> str:
    """仅当用户在本轮明确要求把结论记入知识库，或明确要求修正知识库中的知识时调用。

    不要在分析结束或觉得有价值时自行调用。
    title 是知识说明的短标题，body 是整理后的知识正文，不是用户的指令句。
    智能体绑定了多个知识库时，knowledge_base_name 必须是用户点名的知识库名称。
    把本工具返回的原文原样回复给用户，不要改写，也不要补充队列、审核或旧页是否已改。
    """
    skill_id = _runtime_value(config, "skill_id")
    try:
        skill_pk = int(skill_id)
    except (TypeError, ValueError):
        return REPLY_SWITCH_OFF
    skill = LLMSkill.objects.filter(pk=skill_pk).first()
    return write_chat_wiki_material(
        skill=skill,
        explicit_request=_explicit(explicit_request),
        title=title,
        body=body,
        knowledge_base_name=knowledge_base_name or "",
        actor=_runtime_value(config, WIKI_MATERIAL_ACTOR_KEY),
    )
