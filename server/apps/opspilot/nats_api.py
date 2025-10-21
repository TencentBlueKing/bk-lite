import datetime
import json

import nats_client
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import (
    Bot,
    BotConversationHistory,
    EmbedProvider,
    KnowledgeBase,
    LLMModel,
    LLMSkill,
    OCRProvider,
    QuotaRule,
    RerankProvider,
    SkillTools,
)
from apps.opspilot.utils.bot_utils import get_user_info


@nats_client.register
def init_user_set(group_id, group_name):
    try:
        QuotaRule.objects.create(
            name=f"group-{group_name}-llm-quota",
            target_type="group",
            target_list=[group_id],
            rule_type="shared",
            file_size=50,
            unit="MB",
            skill_count=2,
            bot_count=2,
        )
        return {"result": True}
    except Exception as e:
        logger.exception(e)
        return {"result": False, "message": str(e)}


@nats_client.register
def get_opspilot_module_list():
    return [
        {"name": "bot", "display_name": "Studio"},
        {"name": "skill", "display_name": "Agent"},
        {"name": "knowledge", "display_name": "Knowledge"},
        {"name": "tools", "display_name": "Tool"},
        {
            "name": "provider",
            "display_name": "Model",
            "children": [
                {"name": "llm_model", "display_name": "LLM Model"},
                {"name": "ocr_model", "display_name": "OCR Model"},
                {"name": "embed_model", "display_name": "Embed Model"},
                {"name": "rerank_model", "display_name": "Rerank Model"},
            ],
        },
    ]


@nats_client.register
def get_opspilot_module_data(module, child_module, page, page_size, group_id):
    model_map = {
        "bot": Bot,
        "skill": LLMSkill,
        "knowledge": KnowledgeBase,
        "tools": SkillTools,
    }
    provider_model_map = {
        "llm_model": LLMModel,
        "ocr_model": OCRProvider,
        "embed_model": EmbedProvider,
        "rerank_model": RerankProvider,
    }
    if module != "provider":
        model = model_map[module]
    else:
        model = provider_model_map[child_module]
    queryset = model.objects.filter(team__contains=int(group_id))
    # 计算总数
    total_count = queryset.count()
    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size
    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]

    return {
        "count": total_count,
        "items": list(data_list),
    }


@nats_client.register
def get_guest_provider(group_id):
    default_llm_model = LLMModel.objects.get(name="GPT-4o", is_build_in=True)
    if group_id not in default_llm_model.team:
        default_llm_model.team.append(group_id)
        default_llm_model.save()
    rerank_model = RerankProvider.objects.get(name="bce-reranker-base_v1", is_build_in=True)
    if group_id not in rerank_model.team:
        rerank_model.team.append(group_id)
        rerank_model.save()

    embed_model_1 = EmbedProvider.objects.get(name="bce-embedding-base_v1", is_build_in=True)
    if group_id not in embed_model_1.team:
        embed_model_1.team.append(group_id)
        embed_model_1.save()
    embed_model_2 = EmbedProvider.objects.get(name="FastEmbed(BAAI/bge-small-zh-v1.5)", is_build_in=True)
    if group_id not in embed_model_2.team:
        embed_model_2.team.append(group_id)
        embed_model_2.save()

    paddle_ocr = OCRProvider.objects.get(name="PaddleOCR", is_build_in=True)
    if group_id not in paddle_ocr.team:
        paddle_ocr.team.append(group_id)
        paddle_ocr.save()

    azure_ocr = OCRProvider.objects.get(name="AzureOCR", is_build_in=True)
    if group_id not in azure_ocr.team:
        azure_ocr.team.append(group_id)
        azure_ocr.save()
    olm_ocr = OCRProvider.objects.get(name="OlmOCR", is_build_in=True)
    if group_id not in olm_ocr.team:
        olm_ocr.team.append(group_id)
        olm_ocr.save()
    return {
        "result": True,
        "data": {
            "llm_model": {"id": default_llm_model.id, "name": default_llm_model.name},
            "rerank_model": {"id": rerank_model.id, "name": rerank_model.name},
            "embed_model": [{"id": model.id, "name": model.name} for model in [embed_model_1, embed_model_2]],
            "ocr_model": [{"id": model.id, "name": model.name} for model in [paddle_ocr, azure_ocr, olm_ocr]],
        },
    }


@nats_client.register
def consume_bot_event(kwargs):
    """
    kwargs 参数：
        text： 对话内容
        send_id: 用户ID
        timestamp： 对话时间
        event：("user", "用户"), ("bot", "机器人")
        input_channel：web,enterprise_wechat,dingtalk,wechat_official_account
        citing_knowledge: 引用知识，列表 []
    """
    text = kwargs.get("text", "") or ""
    if not text.strip():
        return
    try:
        sender_id = kwargs["sender_id"]
        if not sender_id.strip():
            return
        bot_id = int(kwargs.get("bot_id", 7))
        created_at = datetime.datetime.fromtimestamp(kwargs["timestamp"], tz=datetime.timezone.utc)

        # 优化 input_channel 获取逻辑
        input_channel = kwargs.get("input_channel")
        if not input_channel:
            return
        user, _ = get_user_info(bot_id, input_channel, sender_id)
        bot = Bot.objects.get(id=bot_id)
        citing_knowledge = kwargs.get("citing_knowledge", [])
        if not citing_knowledge:
            msg = kwargs.get("metadata", {}).get("other_data", {}).get("citing_knowledge", [])
            msg_str = json.dumps(msg).replace("\u0000", " ").replace(r"\u0000", " ")
            citing_knowledge = json.loads(msg_str)
        BotConversationHistory.objects.create(
            bot_id=bot_id,
            channel_user_id=user.id,
            created_at=created_at,
            created_by=bot.created_by,
            domain=bot.domain,
            conversation_role=kwargs["event"],
            conversation=kwargs["text"] or "",
            citing_knowledge=citing_knowledge,
        )
    except Exception as e:
        logger.exception(f"对话历史保存失败: {e}, 传入参数如下：{kwargs}")
