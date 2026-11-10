"""对话生成技能包的成稿工具。不进入工具管理目录。"""

from asgiref.sync import sync_to_async
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from apps.opspilot.services.conversation_skill_package import (
    PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
    prepare_conversation_skill_package,
    publish_conversation_skill_package_choice,
)

_TOOL_DESCRIPTION = (
    "把当前对话整理成一条技能包成稿，并发出确认卡。"
    "只有用户明确说做成技能包、保存成技能包或生成技能包时才能调用。"
    "必须同时给出名称、何时使用的说明、至少一条触发词，以及包含步骤和完成标准的正文。"
    "缺任何一项不要调用，先追问。调用后只表示已请用户确认，不要说已经写入。"
    "普通问答不要调用，也不要主动提议做成技能包。"
)


class ConversationSkillPackageDraft(BaseModel):
    name: str = Field(description="技能包名称")
    description: str = Field(description="什么时候使用这个技能包")
    triggers: list[str] = Field(description="至少一条触发词")
    skill_markdown: str = Field(description="步骤、需要用户提供什么、怎样算做完。不要写死某个工具。")


def build_prepare_conversation_skill_package_tool():
    async def _prepare(
        name: str,
        description: str,
        triggers: list[str],
        skill_markdown: str,
        config: RunnableConfig = None,
    ) -> str:
        configurable = {}
        if isinstance(config, dict):
            configurable = dict(config.get("configurable") or {})
        graph_request = configurable.get("graph_request")
        prepared = await sync_to_async(prepare_conversation_skill_package, thread_sensitive=True)(
            name=name,
            description=description,
            triggers=triggers,
            skill_markdown=skill_markdown,
            graph_request=graph_request,
            config=config if isinstance(config, dict) else {"configurable": configurable},
        )
        if not prepared.get("ok"):
            return str(prepared.get("text") or "")
        visible, _tool_message = publish_conversation_skill_package_choice(
            prepared,
            graph_request=graph_request,
            config=config if isinstance(config, dict) else {"configurable": configurable},
            messages=[],
            tool_call_id="",
        )
        return visible

    return StructuredTool.from_function(
        coroutine=_prepare,
        name=PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
        description=_TOOL_DESCRIPTION,
        args_schema=ConversationSkillPackageDraft,
    )
