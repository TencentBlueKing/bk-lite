import datetime
import hashlib
import json
import time

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.utils.translation import gettext as _
from django_minio_backend import MinioBackend

from apps.base.models import UserAPISecret
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.async_utils import create_async_compatible_generator
from apps.core.utils.exempt import api_exempt
from apps.opspilot.models import Bot, BotChannel, BotConversationHistory, BotWorkFlow, LLMSkill
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.services.skill_excute_service import SkillExecuteService
from apps.opspilot.utils.bot_utils import get_client_ip, insert_skill_log, set_time_range
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.sse_chat import generate_stream_error, stream_chat
from apps.rpc.system_mgmt import SystemMgmt


@api_exempt
def get_bot_detail(request, bot_id):
    api_token = request.META.get("HTTP_AUTHORIZATION").split("TOKEN")[-1].strip()
    if not api_token:
        return JsonResponse({})
    bot = Bot.objects.filter(id=bot_id, api_token=api_token).first()
    if not bot:
        return JsonResponse({})
    channels = BotChannel.objects.filter(bot_id=bot_id, enabled=True)
    return_data = {
        "channels": [
            {
                "id": i.id,
                "name": i.name,
                "channel_type": i.channel_type,
                "channel_config": i.decrypted_channel_config,
            }
            for i in channels
        ],
    }
    return JsonResponse(return_data)


@api_exempt
def model_download(request):
    bot_id = request.GET.get("bot_id")
    bot = Bot.objects.filter(id=bot_id).first()
    if not bot:
        return JsonResponse({})
    rasa_model = bot.rasa_model
    if not rasa_model:
        return JsonResponse({})
    storage = MinioBackend(bucket_name="munchkin-private")
    file = storage.open(rasa_model.model_file.name, "rb")

    # Calculate ETag
    data = file.read()
    etag = hashlib.md5(data).hexdigest()

    # Reset file pointer to start
    file.seek(0)

    response = FileResponse(file)
    response["ETag"] = etag

    return response


def validate_openai_token(token, team=None):
    """Validate the OpenAI API token"""
    if not token:
        return False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}
    token = token.split("Bearer ")[-1]
    user = UserAPISecret.objects.filter(api_secret=token).first()
    if not user:
        if team is None:
            return False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}
        client = SystemMgmt()
        result = client.verify_token(token)
        if not result.get("result"):
            return False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}
        user_info = result.get("data")
        user = UserAPISecret(
            username=user_info["username"],
            team=int(team),
        )
    return True, user


def validate_header_token(token, bot_id):
    if not token:
        return False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}
    bot_obj = Bot.objects.filter(id=bot_id, online=True).first()
    if not bot_obj:
        return False, {"choices": [{"message": {"role": "assistant", "content": "No bot online"}}]}
    token = token.split("Bearer ")[-1]
    client = SystemMgmt()
    # res = client.verify_token(token)
    res = client.get_pilot_permission_by_token(token, bot_id, bot_obj.team)
    if not res.get("result"):
        return False, {"choices": [{"message": {"role": "assistant", "content": "No authorization"}}]}
    return True, {"username": res["data"]["username"]}


def get_skill_and_params(kwargs, team, bot_id=None):
    """Get skill object and prepare parameters for LLM invocation"""
    skill_id = kwargs.get("model")
    if not bot_id:
        skill_obj = LLMSkill.objects.filter(name=skill_id, team__contains=int(team)).first()
    else:
        skill_obj = LLMSkill.objects.filter(name=skill_id, bot=bot_id).first()

    if not skill_obj:
        return (
            None,
            None,
            {"choices": [{"message": {"role": "assistant", "content": "No skill"}}]},
        )
    num = kwargs.get("conversation_window_size") or skill_obj.conversation_window_size
    chat_history = [{"message": i["content"], "event": i["role"]} for i in kwargs.get("messages", [])[-1 * num :]]

    params = {
        "llm_model": skill_obj.llm_model_id,
        "skill_prompt": kwargs.get("prompt", "") or kwargs.get("skill_prompt", "") or skill_obj.skill_prompt,
        "temperature": kwargs.get("temperature") or skill_obj.temperature,
        "chat_history": chat_history,
        "user_message": chat_history[-1]["message"],
        "conversation_window_size": kwargs.get("conversation_window_size") or skill_obj.conversation_window_size,
        "enable_rag": kwargs.get("enable_rag") or skill_obj.enable_rag,
        "rag_score_threshold": [{"knowledge_base": int(key), "score": float(value)} for key, value in skill_obj.rag_score_threshold_map.items()],
        "enable_rag_knowledge_source": skill_obj.enable_rag_knowledge_source,
        "show_think": skill_obj.show_think,
        "tools": skill_obj.tools,
        "skill_type": skill_obj.skill_type,
        "group": skill_obj.team[0],
    }

    return skill_obj, params, None


def invoke_chat(params, skill_obj, kwargs, current_ip, user_message):
    return_data, _ = get_chat_msg(current_ip, kwargs, params, skill_obj, user_message)
    return JsonResponse(return_data)


def format_knowledge_sources(content, skill_obj, doc_map=None, title_map=None):
    """Format and append knowledge source references if enabled"""
    if skill_obj.enable_rag_knowledge_source:
        knowledge_titles = {doc_map.get(k, {}).get("name") for k in title_map.keys()}
        last_content = content.strip().split("\n")[-1]
        if "引用知识" not in last_content and knowledge_titles:
            content += f'\n引用知识: {", ".join(knowledge_titles)}'
    return content


def get_chat_msg(current_ip, kwargs, params, skill_obj, user_message):
    data, doc_map, title_map = llm_service.invoke_chat(params)
    content = format_knowledge_sources(data["message"], skill_obj, doc_map, title_map)
    return_data = {
        "id": skill_obj.name,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": kwargs["model"],
        "usage": {
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "total_tokens": data["prompt_tokens"] + data["completion_tokens"],
            "completion_tokens_details": {
                "reasoning_tokens": 0,
                "accepted_prediction_tokens": 0,
                "rejected_prediction_tokens": 0,
            },
        },
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "logprobs": None,
                "finish_reason": "stop",
                "index": 0,
            }
        ],
    }
    insert_skill_log(current_ip, skill_obj.id, return_data, kwargs, user_message=user_message)
    return return_data, content


@api_exempt
def openai_completions(request):
    """Main entry point for OpenAI completions"""
    kwargs = json.loads(request.body)
    current_ip = get_client_ip(request)

    stream_mode = kwargs.get("stream", False)
    token = request.META.get("HTTP_AUTHORIZATION") or request.META.get(settings.API_TOKEN_HEADER_NAME)

    is_valid, msg = validate_openai_token(token)
    if not is_valid:
        if stream_mode:
            return generate_stream_error(msg["choices"][0]["message"]["content"])
        else:
            return JsonResponse(msg)
    user = msg
    try:
        skill_obj, params, error = get_skill_and_params(kwargs, user.team)
        if error:
            if skill_obj:
                user_message = params.get("user_message")
                insert_skill_log(current_ip, skill_obj.id, error, kwargs, False, user_message)
            if stream_mode:
                return generate_stream_error(error["choices"][0]["message"]["content"])
            else:
                return JsonResponse(error)
    except Exception as e:
        if stream_mode:
            return generate_stream_error(str(e))
        else:
            return JsonResponse({"choices": [{"message": {"role": "assistant", "content": str(e)}}]})
    params["user_id"] = user.username
    params["enable_km_route"] = skill_obj.enable_km_route
    params["km_llm_model"] = skill_obj.km_llm_model
    params["enable_suggest"] = skill_obj.enable_suggest
    params["enable_query_rewrite"] = skill_obj.enable_query_rewrite
    user_message = params.get("user_message")
    if not stream_mode:
        return invoke_chat(params, skill_obj, kwargs, current_ip, user_message)
    return stream_chat(params, skill_obj.name, kwargs, current_ip, user_message)


@api_exempt
def lobe_skill_execute(request):
    kwargs = json.loads(request.body)
    current_ip = get_client_ip(request)

    stream_mode = kwargs.get("stream", False)
    # stream_mode = False
    token = request.META.get("HTTP_AUTHORIZATION") or request.META.get(settings.API_TOKEN_HEADER_NAME)
    is_valid, msg = validate_header_token(token, int(kwargs["studio_id"]))
    if not is_valid:
        if stream_mode:
            return generate_stream_error(msg["choices"][0]["message"]["content"])
        else:
            return JsonResponse(msg)
    user = msg
    try:
        skill_obj, params, error = get_skill_and_params(kwargs, "", kwargs.get("studio_id"))
        if error:
            if skill_obj:
                user_message = params.get("user_message")
                insert_skill_log(current_ip, skill_obj.id, error, kwargs, False, user_message)
            if stream_mode:
                return generate_stream_error(error["choices"][0]["message"]["content"])
            else:
                return JsonResponse(error)
    except Exception as e:
        if stream_mode:
            return generate_stream_error(str(e))
        else:
            return JsonResponse({"choices": [{"message": {"role": "assistant", "content": str(e)}}]})
    params["user_id"] = user["username"]
    params["enable_km_route"] = skill_obj.enable_km_route
    params["km_llm_model"] = skill_obj.km_llm_model
    params["enable_suggest"] = skill_obj.enable_suggest
    params["enable_query_rewrite"] = skill_obj.enable_query_rewrite
    user_message = params.get("user_message")
    if not stream_mode:
        return invoke_chat(params, skill_obj, kwargs, current_ip, user_message)
    return stream_chat(params, skill_obj.name, kwargs, current_ip, user_message)


@api_exempt
def skill_execute(request):
    kwargs = json.loads(request.body)
    logger.info(f"skill_execute kwargs: {kwargs}")
    skill_id = kwargs.get("skill_id")
    user_message = kwargs.get("user_message")
    sender_id = kwargs.get("sender_id", "")
    chat_history = kwargs.get("chat_history", [])
    bot_id = kwargs.get("bot_id")
    channel = kwargs.get("channel", "socketio")
    if channel in ["socketio", "rest"]:
        channel = "web"
    return_data = get_skill_execute_result(
        bot_id,
        channel,
        chat_history,
        kwargs,
        request,
        sender_id,
        skill_id,
        user_message,
    )
    return JsonResponse({"result": return_data})


def get_skill_execute_result(bot_id, channel, chat_history, kwargs, request, sender_id, skill_id, user_message):
    api_token = request.META.get("HTTP_AUTHORIZATION").split("TOKEN")[-1].strip()
    if not api_token:
        return {"content": "No authorization"}
    bot = Bot.objects.filter(id=bot_id, api_token=api_token).first()
    if not bot:
        logger.info(f"api_token: {api_token}")
        return {"content": "No bot found"}
    try:
        result = SkillExecuteService.execute_skill(bot, skill_id, user_message, chat_history, sender_id, channel)
    except Exception as e:
        logger.exception(e)
        result = {"content": str(e)}
    if getattr(request, "api_pass", False):
        current_ip = get_client_ip(request)
        insert_skill_log(
            current_ip,
            bot.llm_skills.first().id,
            result,
            kwargs,
            user_message=user_message,
        )
    return result


# @HasRole("admin")
def get_total_token_consumption(request):
    return JsonResponse({"result": True, "data": 0})


# @HasRole("admin")
def get_token_consumption_overview(request):
    return JsonResponse({"result": True, "data": []})


# @HasRole("admin")
def get_conversations_line_data(request):
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = set_time_range(end_time_str, start_time_str)
    queryset = (
        BotConversationHistory.objects.filter(
            created_at__range=[start_time, end_time],
            bot_id=request.GET.get("bot_id"),
            conversation_role="bot",
        )
        .annotate(date=TruncDate("created_at"))
        .values("channel_user__channel_type", "date")
        .annotate(count=Count("id"))  # 不去重，按记录统计
    )
    # 生成日期范围内的所有日期
    result = set_channel_type_line(end_time, queryset, start_time)
    return JsonResponse({"result": True, "data": result})


# @HasRole("admin")
def get_active_users_line_data(request):
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = set_time_range(end_time_str, start_time_str)
    queryset = (
        BotConversationHistory.objects.filter(
            created_at__range=[start_time, end_time],
            bot_id=request.GET.get("bot_id"),
            conversation_role="user",
        )
        .annotate(date=TruncDate("created_at"))
        .values("channel_user__channel_type", "date")
        .annotate(count=Count("channel_user", distinct=True))
    )
    # 生成日期范围内的所有日期
    result = set_channel_type_line(end_time, queryset, start_time)
    return JsonResponse({"result": True, "data": result})


def set_channel_type_line(end_time, queryset, start_time):
    num_days = (end_time - start_time).days + 1
    all_dates = [start_time + datetime.timedelta(days=i) for i in range(num_days)]
    formatted_dates = {date.strftime("%Y-%m-%d"): 0 for date in all_dates}
    known_channel_types = [
        "web",
        "ding_talk",
        "enterprise_wechat",
        "wechat_official_account",
    ]
    result_dict = {channel_type: formatted_dates.copy() for channel_type in known_channel_types}
    total_user_count = formatted_dates.copy()
    # 更新字典与查询结果
    for entry in queryset:
        channel_type = entry["channel_user__channel_type"]
        date = entry["date"].strftime("%Y-%m-%d")
        user_count = entry["count"]
        result_dict[channel_type][date] = user_count
        total_user_count[date] += user_count
    # 转换为所需的输出格式
    result = {
        channel_type: [{"time": date, "count": user_count} for date, user_count in sorted(date_dict.items())]
        for channel_type, date_dict in result_dict.items()
    }
    result["total"] = [{"time": date, "count": user_count} for date, user_count in sorted(total_user_count.items())]
    return result


@api_exempt
def execute_chat_flow(request, bot_id, node_id):
    """执行ChatFlow流程"""
    if not bot_id or not node_id:
        return JsonResponse({"result": False, "message": _("Bot ID and Node ID are required.")})
    kwargs = json.loads(request.body)
    message = kwargs.get("message", "")
    is_test = kwargs.get("is_test", False)
    # 验证token
    token = request.META.get("HTTP_AUTHORIZATION") or request.META.get(settings.API_TOKEN_HEADER_NAME)
    is_valid, msg = validate_openai_token(token, request.COOKIES.get("current_team") or None)
    if not is_valid:
        return JsonResponse(msg)

    # 验证Bot
    user = msg
    filter_dict = {
        "id": bot_id,
        "team__contains": int(user.team),
    }
    if not is_test:
        filter_dict["online"] = True
    bot_obj = Bot.objects.filter(**filter_dict).first()
    if not bot_obj:
        return JsonResponse({"result": False, "message": _("No bot online")})

    # 获取Bot的工作流配置
    bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot_obj.id).first()
    if not bot_chat_flow:
        return JsonResponse({"result": False, "message": _("No chat flow configured for this bot.")})

    # 检查工作流是否有配置数据
    if not bot_chat_flow.flow_json:
        return JsonResponse({"result": False, "message": _("Chat flow configuration is empty.")})

    try:
        # 创建ChatFlow引擎 - 使用数据库中的工作流配置
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 获取当前节点类型
        node_obj = engine._get_node_by_id(node_id)
        node_type = node_obj.get("type") if node_obj else None

        # 准备输入数据
        input_data = {
            "last_message": message,
            "user_id": user.username,
            "bot_id": bot_id,
            "node_id": node_id,
        }

        logger.info(f"开始执行ChatFlow流程，bot_id: {bot_id}, node_id: {node_id}, user: {user.username}, node_type: {node_type}")
        result = engine.execute(input_data)

        # 仅区分 openai 类型，其余类型统一走原有逻辑
        if node_type == "openai":

            def sse_generator():
                yield f"data: {result}\n\n"
                yield "data: [DONE]\n\n"

            async_generator = create_async_compatible_generator(sse_generator())
            response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
            response["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response["X-Accel-Buffering"] = "no"
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Headers"] = "Cache-Control"
            return response
        logger.info(f"ChatFlow流程执行完成，bot_id: {bot_id}, 最终输出: {result}")
        return JsonResponse({"result": True, "data": {"content": result, "execution_time": time.time()}})

    except Exception as e:
        logger.error(f"ChatFlow流程执行失败，bot_id: {bot_id}, node_id: {node_id}, 错误: {str(e)}")
        logger.exception(e)
        # 流式错误响应，参考 llm_view.py
        from apps.opspilot.viewsets.llm_view import LLMViewSet

        return LLMViewSet._create_error_stream_response(str(e))


@api_exempt
def get_chat_flow_task_status(request):
    """获取ChatFlow任务状态"""
    task_id = request.GET.get("task_id", "")

    if not task_id:
        return JsonResponse({"result": False, "message": _("Task ID is required.")})

    try:
        from celery.result import AsyncResult

        # 获取任务结果
        task_result = AsyncResult(task_id)

        response_data = {
            "result": True,
            "data": {
                "task_id": task_id,
                "status": task_result.status,
                "ready": task_result.ready(),
                "successful": task_result.successful() if task_result.ready() else None,
            },
        }

        # 如果任务完成，返回结果
        if task_result.ready():
            if task_result.successful():
                response_data["data"]["result"] = task_result.result
            else:
                response_data["data"]["error"] = str(task_result.result)

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"获取ChatFlow任务状态失败，task_id: {task_id}, 错误: {str(e)}")

        return JsonResponse({"result": False, "message": f"获取任务状态失败: {str(e)}", "error_details": {"task_id": task_id, "error": str(e)}})


@api_exempt
def test(request):
    kwargs = request.GET.dict()
    data = json.loads(request.body) if request.body else {}
    kwargs.update(data)
    return JsonResponse({"result": True, "data": kwargs})
