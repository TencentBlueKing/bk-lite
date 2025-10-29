from django.conf import settings

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMSkill, SkillRule
from apps.opspilot.services.llm_service import llm_service
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

        result = llm_service.chat(params)
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
        if channel == "web":
            return llm_skill.skill_prompt, [
                {"knowledge_base": int(key), "score": float(value)} for key, value in llm_skill.rag_score_threshold_map.items()
            ]
        rules = SkillRule.objects.filter(skill_id=llm_skill.id, is_enabled=True).order_by("-id")
        bot_rule = cls.get_bot_rule(rules, user, channel, groups)
        all_knowledge_list = [int(i) for i in llm_skill.rag_score_threshold_map.keys()]

        if bot_rule is None:
            skill_prompt = llm_skill.skill_prompt
            filter_knowledge_list = all_knowledge_list
        else:
            skill_prompt = bot_rule.action_set.get("skill_prompt") or llm_skill.skill_prompt
            filter_knowledge_list = bot_rule.action_set.get("knowledge_base_list", all_knowledge_list)
        rag_score_threshold = [
            {"knowledge_base": int(key), "score": float(value)}
            for key, value in llm_skill.rag_score_threshold_map.items()
            if int(key) in filter_knowledge_list
        ]
        return skill_prompt, rag_score_threshold

    @staticmethod
    def get_bot_rule(rules, user, channel, groups):
        if not user:
            return None
        for i in rules:
            condition = i.condition
            if condition["operator"] == "or":
                for u in condition["conditions"]:
                    if u["type"] != channel:
                        continue
                    if u["obj"] == "user" and u["value"] in user.name:
                        return i
                    if u["obj"] == "group":
                        for group in groups:
                            if u["value"] in group["name"]:
                                return i
            else:
                flag = True
                for u in condition["conditions"]:
                    if u["type"] != channel:
                        return
                    if u["obj"] == "user":
                        flag = flag and u["value"] in user.name
                    else:
                        group_flag = False
                        for group in groups:
                            if u["value"] in group["name"]:
                                group_flag = True
                                break
                        flag = flag and group_flag
                if flag:
                    return i
        return None
