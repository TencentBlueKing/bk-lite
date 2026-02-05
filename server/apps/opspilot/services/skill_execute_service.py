from django.conf import settings

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

        skill_prompt, rag_score_threshold = cls.get_rule_result(channel, llm_skill, user, groups)

        params = {
            "user_message": user_message,
            "skill_type": llm_skill.skill_type,
            "llm_model": llm_skill.llm_model_id,
            "skill_prompt": skill_prompt,
            "enable_rag": llm_skill.enable_rag,
            "enable_rag_knowledge_source": llm_skill.enable_rag_knowledge_source,
            "enable_rag_strict_mode": llm_skill.enable_rag_strict_mode,
            "rag_score_threshold": rag_score_threshold,
            "chat_history": chat_history,
            "conversation_window_size": 10,
            "temperature": llm_skill.temperature,
            "username": user.name if user else sender_id,
            "user_id": user.user_id if user else sender_id,
            "bot_id": bot.id,
            "show_think": llm_skill.show_think,
            "tools": llm_skill.tools,
            "group": llm_skill.team[0],
            "enable_km_route": llm_skill.enable_km_route,
            "km_llm_model": llm_skill.km_llm_model,
            "enable_suggest": llm_skill.enable_suggest,
            "enable_query_rewrite": llm_skill.enable_query_rewrite,
        }

        result = chat_service.chat(params)
        content = result["content"]
        if llm_skill.enable_rag_knowledge_source:
            knowledge_titles = {x["knowledge_title"] for x in result["citing_knowledge"]}
            last_content = content.strip().split("\n")[-1]
            if "引用知识" not in last_content and knowledge_titles:
                content += "\n"
                if channel == "enterprise_wechat":
                    title = cls.format_enterprise_wechat_title(result["citing_knowledge"])
                else:
                    title = knowledge_titles
                content += f'引用知识: {", ".join(title)}'
        result["content"] = content
        return result

    @classmethod
    def format_enterprise_wechat_title(cls, citing_knowledge):
        return_data = []
        for i in citing_knowledge:
            url = f"{settings.OPSPILOT_WEB_URL.rstrip('/')}/opspilot/knowledge/preview?id={i['knowledge_id']}"
            return_data.append(f"[{i['knowledge_title']}]({url})")
        return return_data

    @classmethod
    def get_rule_result(cls, channel, llm_skill, user, groups):
        # 移除规则逻辑,直接返回 skill 的配置
        return llm_skill.skill_prompt, [
            {"knowledge_base": int(key), "score": float(value)} for key, value in llm_skill.rag_score_threshold_map.items()
        ]
