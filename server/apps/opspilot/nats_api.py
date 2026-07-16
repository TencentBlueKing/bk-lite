import datetime
import json
import uuid

import nats_client
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotConversationHistory, BotWorkFlow, EmbedProvider, LLMModel, LLMSkill, OCRProvider, RerankProvider, SkillTools
from apps.opspilot.models.bot_mgmt import BotWebChatSession
from apps.opspilot.utils.bot_utils import get_user_info
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine


def _read_nats_node_expose_flag(bot_id, node_id):
    """读取 NATS 触发节点的 ``data.config.expose_as_web_chat`` 字段。

    仅当该字段显式为 True 时返回 True；缺省、False、或工作流/节点找不到都返回 False。
    """
    try:
        workflow = BotWorkFlow.objects.filter(bot_id=bot_id).order_by("-id").first()
    except Exception:  # noqa: BLE001
        return False
    if not workflow or not isinstance(workflow.flow_json, dict):
        return False
    nodes = workflow.flow_json.get("nodes", []) or []
    for node in nodes:
        if node.get("id") != node_id:
            continue
        config = (node.get("data") or {}).get("config") or {}
        return bool(config.get("expose_as_web_chat"))
    return False


def _normalize_nats_trigger_input(message, team, user_ids, bot_id, node_id):
    if not isinstance(message, str) or not message.strip():
        return None, {"result": False, "message": "message is required"}

    # team 现在只允许单个组织 ID；兼容历史的单元素列表写法
    if isinstance(team, (list, tuple)):
        if len(team) != 1:
            return None, {"result": False, "message": "team must be a single team id"}
        team = team[0]
    team_value = str(team).strip()
    if not team_value or not team_value.isdigit():
        return None, {"result": False, "message": "team must be a single integer team id"}
    normalized_team = int(team_value)

    if not isinstance(user_ids, list):
        return None, {"result": False, "message": "user_ids must be a list"}

    normalized_user_ids = []
    for user_id in user_ids:
        if user_id is None:
            continue
        user_value = str(user_id).strip()
        if user_value:
            normalized_user_ids.append(user_value)

    try:
        normalized_bot_id = int(bot_id)
    except (TypeError, ValueError):
        return None, {"result": False, "message": "bot_id must be an integer"}

    normalized_node_id = str(node_id).strip() if node_id is not None else ""
    if not normalized_node_id:
        return None, {"result": False, "message": "node_id is required"}

    return {
        "message": message.strip(),
        "team": normalized_team,
        "user_ids": normalized_user_ids,
        "bot_id": normalized_bot_id,
        "node_id": normalized_node_id,
    }, None


@nats_client.register
def get_opspilot_module_list():
    return [
        {"name": "bot", "display_name": "Studio"},
        {"name": "skill", "display_name": "Agent"},
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
        "tools": SkillTools,
    }
    provider_model_map = {
        "llm_model": LLMModel,
        "ocr_model": OCRProvider,
        "embed_model": EmbedProvider,
        "rerank_model": RerankProvider,
    }
    if module != "provider":
        model = model_map.get(module)
        if model is None:
            return {"result": False, "message": f"Unknown module: {module}"}
    else:
        model = provider_model_map.get(child_module)
        if model is None:
            return {"result": False, "message": f"Unknown child_module: {child_module}"}
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
        bot_id: （必填）目标 Bot 的 ID，缺失时拒绝处理并返回错误
        text： 对话内容
        send_id: 用户ID
        timestamp： 对话时间
        event：("user", "用户"), ("bot", "机器人")
        input_channel：web,enterprise_wechat,dingtalk,wechat_official_account
    """
    text = kwargs.get("text", "") or ""
    if not text.strip():
        return {"result": True}
    try:
        sender_id = kwargs["sender_id"]
        if not sender_id.strip():
            return {"result": True}
        raw_bot_id = kwargs.get("bot_id")
        if not raw_bot_id:
            return {"result": False, "message": "bot_id is required"}
        bot_id = int(raw_bot_id)
        created_at = datetime.datetime.fromtimestamp(kwargs["timestamp"], tz=datetime.timezone.utc)

        # 优化 input_channel 获取逻辑
        input_channel = kwargs.get("input_channel")
        if not input_channel:
            return {"result": True}
        user, _ = get_user_info(bot_id, input_channel, sender_id)
        bot = Bot.objects.get(id=bot_id)
        BotConversationHistory.objects.create(
            bot_id=bot_id,
            channel_user_id=user.id,
            created_at=created_at,
            created_by=bot.created_by,
            domain=bot.domain,
            conversation_role=kwargs["event"],
            conversation=kwargs["text"] or "",
        )
    except (KeyError, ValueError, TypeError, AttributeError, Bot.DoesNotExist, json.JSONDecodeError) as e:
        # 预期内的数据/解析错误：记录详细堆栈并向 NATS 调用方回传失败结果，
        # 避免对话历史被静默丢弃。
        logger.exception(f"对话历史保存失败: {e}, 传入参数如下：{kwargs}")
        return {"result": False, "message": str(e)}
    return {"result": True}


@nats_client.register
def trigger_workflow_by_nats(message, team, user_ids, bot_id, node_id):
    """由告警中心通过 NATS 触发 OpsPilot workflow。

    Args:
        message: 告警消息文本
        team: 相关团队 ID（单个整数，仅允许一个组织）
        user_ids: 相关用户 ID 列表
        bot_id: 目标 Bot 的 ID
        node_id: 起始节点 ID
    """
    normalized_input, error = _normalize_nats_trigger_input(message, team, user_ids, bot_id, node_id)
    if error:
        return error

    workflow = BotWorkFlow.objects.filter(bot_id=normalized_input["bot_id"]).order_by("-id").first()
    if not workflow:
        return {"result": False, "message": "Bot workflow not found"}

    expose_as_web_chat = bool(_read_nats_node_expose_flag(normalized_input["bot_id"], normalized_input["node_id"]) and normalized_input["user_ids"])

    session_id = ""
    if expose_as_web_chat:
        session_id = uuid.uuid4().hex
        title = normalized_input["message"][:50]
        BotWebChatSession.objects.create(
            session_id=session_id,
            bot_id=normalized_input["bot_id"],
            node_id=normalized_input["node_id"],
            source=BotWebChatSession.SOURCE_NATS,
            participants=list(normalized_input["user_ids"]),
            title=title,
            created_by="nats",
        )

    engine = create_chat_flow_engine(workflow, normalized_input["node_id"], entry_type="nats")
    input_data = {
        "last_message": normalized_input["message"],
        "message": normalized_input["message"],
        "team": normalized_input["team"],
        "user_ids": normalized_input["user_ids"],
        "bot_id": normalized_input["bot_id"],
        "node_id": normalized_input["node_id"],
        "entry_type": "nats",
        "is_third_party": True,
    }
    if session_id:
        input_data["session_id"] = session_id
        # 首位 user_id 作为首条 user 消息的 user_id，避免 ExecutionRepository 早返吞掉历史
        input_data["user_id"] = normalized_input["user_ids"][0]

    execution_result = engine.execute(input_data)

    response = {
        "result": execution_result.get("success", True) if isinstance(execution_result, dict) else True,
        "data": execution_result,
        "entry_type": "nats",
        "execution_id": engine.execution_id,
    }
    if session_id:
        response["session_id"] = session_id
        response["exposed_as_web_chat"] = True
    return response
