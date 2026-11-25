"""整理对话提炼操作步骤生成技能包。"""

from apps.opspilot.metis.llm.tools.conversation_skill_package_tool import build_prepare_conversation_skill_package_tool

prepare_conversation_skill_package = build_prepare_conversation_skill_package_tool()

__all__ = ["prepare_conversation_skill_package"]
