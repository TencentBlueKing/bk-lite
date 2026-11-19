"""把当前对话整理成技能包成稿，用户点确认后才写入。智能体没有勾选本工具时不要调用。"""

from apps.opspilot.metis.llm.tools.conversation_skill_package_tool import build_prepare_conversation_skill_package_tool

prepare_conversation_skill_package = build_prepare_conversation_skill_package_tool()

__all__ = ["prepare_conversation_skill_package"]
