from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMSkill
from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.utils.bot_utils import get_user_info


class SkillExecuteService:
    @classmethod
    def execute_skill(cls, bot, action_name, user_message, chat_history, sender_id, channel):
        logger.info(f"执行[{bot.id}]的[{action_name}]动作,发送者ID:[{sender_id}],消息: {user_message}")
        llm_skill: LLMSkill = bot.llm_skills.first()
        user, groups = get_user_info(bot.id, channel, sender_id)

        skill_prompt = cls.get_rule_result(channel, llm_skill, user, groups)

        params = {
            "user_message": user_message,
            "skill_type": llm_skill.skill_type,
            "llm_model": llm_skill.llm_model_id,
            "skill_prompt": skill_prompt,
            "chat_history": chat_history,
            "conversation_window_size": 10,
            "temperature": llm_skill.temperature,
            "username": user.name if user else sender_id,
            "user_id": user.user_id if user else sender_id,
            "bot_id": bot.id,
            "show_think": llm_skill.show_think,
            "tools": llm_skill.tools,
            "group": llm_skill.team[0],
            "enable_suggest": llm_skill.enable_suggest,
            "enable_query_rewrite": llm_skill.enable_query_rewrite,
        }

        return chat_service.chat(params)

    @classmethod
    def get_rule_result(cls, channel, llm_skill, user, groups):
        # 移除规则逻辑,直接返回 skill 的配置
        return llm_skill.skill_prompt
