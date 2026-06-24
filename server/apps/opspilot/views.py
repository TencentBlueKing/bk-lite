import datetime
import json
import time
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from django.core import signing
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import FileResponse, HttpResponse, JsonResponse
from ipware import get_client_ip
from wechatpy.enterprise import WeChatCrypto

from apps.base.models import UserAPISecret
from apps.core.decorators.api_permission import HasRole
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.exempt import api_exempt
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models import Bot, BotChannel, BotConversationHistory, BotWorkFlow, LLMSkill, SkillRequestLog, WorkFlowTaskResult
from apps.opspilot.serializers.request_serializers import (
    InterruptChatFlowRequestSerializer,
    SubmitApprovalRequestSerializer,
    SubmitChoiceRequestSerializer,
)
from apps.opspilot.services.chat_completion_service import ChatCompletionService
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils, start_dingtalk_stream_client
from apps.opspilot.services.skill_execute_service import SkillExecuteService
from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils
from apps.opspilot.services.workflow_attachment_service import resolve_signed_attachment_token
from apps.opspilot.tasks import chat_flow_test_execute_task
from apps.opspilot.utils.bot_utils import insert_skill_log, set_time_range
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.execution_interrupt import request_interrupt
from apps.opspilot.utils.pending_hitl import try_deliver_to_pending
from apps.opspilot.utils.sse_chat import create_error_stream_response, generate_stream_error, stream_chat
from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import User


def parse_json_body(request, default=None):
    if default is None:
        default = {}
    if not request.body:
        return default, None
    try:
        return json.loads(request.body), None
    except json.JSONDecodeError:
        return None, "Invalid JSON payload"


def extract_api_token(request) -> str:
    auth_header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if not auth_header:
        return ""
    if "TOKEN" in auth_header:
        return auth_header.split("TOKEN", 1)[-1].strip()
    if auth_header.startswith("Bearer "):
        return auth_header.split("Bearer ", 1)[-1].strip()
    return auth_header


def pick_request_value(payload: dict[str, Any], key: str, fallback: Any) -> Any:
    value = payload.get(key)
    return fallback if value is None else value


def safe_conversation_window_size(payload: dict[str, Any], fallback: int) -> int:
    value = payload.get("conversation_window_size")
    if value is None:
        return fallback
    try:
        num = int(value)
    except (TypeError, ValueError):
        return fallback
    return num if num > 0 else fallback


def get_loader(request=None, default_lang="en"):
    """获取语言加载器实例

    Args:
        request: Django request对象
        default_lang: 默认语言

    Returns:
        LanguageLoader实例
    """
    locale = default_lang
    if request and hasattr(request, "user") and request.user:
        locale = getattr(request.user, "locale", default_lang) or default_lang
    return LanguageLoader(app="opspilot", default_lang=locale)


@api_exempt
def get_bot_detail(request, bot_id):
    api_token = extract_api_token(request)
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
                "channel_config": i.format_channel_config(),
            }
            for i in channels
        ],
    }
    return JsonResponse(return_data)


@api_exempt
def download_workflow_attachment(request, download_token):
    try:
        asset = resolve_signed_attachment_token(download_token)
    except signing.SignatureExpired:
        return JsonResponse({"result": False, "message": "Download link expired"}, status=403)
    except signing.BadSignature:
        return JsonResponse({"result": False, "message": "Invalid download token"}, status=403)
    if not asset:
        return JsonResponse({"result": False, "message": "Attachment not found"}, status=404)

    asset.file.open("rb")
    response = FileResponse(asset.file, as_attachment=True, filename=asset.filename)
    if asset.mime_type:
        response["Content-Type"] = asset.mime_type
    return response


def validate_openai_token(token, team=None, is_mobile=False):
    """Validate the OpenAI API token"""
    loader = LanguageLoader(app="opspilot", default_lang="en")
    if not token:
        return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
    token = token.split("Bearer ")[-1]
    user = UserAPISecret.objects.filter(api_secret=token).first()
    if not user:
        if team is None and not is_mobile:
            return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
        team = team or 0
        client = SystemMgmt()
        result = client.verify_token(token)
        if not result.get("result"):
            return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
        user_info = result.get("data")
        user = UserAPISecret(
            username=user_info["username"],
            domain=user_info["domain"],
            team=int(team),
        )
        # Token 认证：从 verify_token 结果获取 locale 和 group_list
        user.locale = user_info.get("locale", "en")
        user.group_list = user_info.get("group_list", [])
    else:
        # UserAPISecret 认证：查询用户信息获取 locale
        user.locale = _get_user_locale(user.username, user.domain)
    return True, user


def _get_user_locale(username: str, domain: str) -> str:
    """获取用户语言设置

    从 User 表查询用户的 locale 设置。

    Args:
        username: 用户名
        domain: 域名

    Returns:
        用户语言设置，默认 "en"
    """

    try:
        user_obj = User.objects.filter(username=username, domain=domain).first()
        if user_obj:
            return user_obj.locale or "en"
    except Exception as e:
        logger.warning(f"Failed to get user locale for {username}@{domain}: {e}")
    return "en"


def validate_header_token(token, bot_id):
    loader = LanguageLoader(app="opspilot", default_lang="en")
    if not token:
        return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
    bot_obj = Bot.objects.filter(id=bot_id, online=True).first()
    if not bot_obj:
        return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.bot_not_online", "No bot online")}}]}
    token = token.split("Bearer ")[-1]
    client = SystemMgmt()
    # res = client.verify_token(token)
    res = client.get_pilot_permission_by_token(token, bot_id, bot_obj.team)
    if not res.get("result"):
        return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
    return True, {"username": res["data"]["username"]}


def get_skill_and_params(kwargs, team, bot_id=None):
    """Get skill object and prepare parameters for LLM invocation

    支持通过 name 或 instance_id 查询 skill
    """
    loader = LanguageLoader(app="opspilot", default_lang="en")
    skill_id = kwargs.get("model")
    if not skill_id:
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.skill_not_found", "No skill")}}]})

    # 尝试通过 name 或 instance_id 查询
    if not bot_id:
        # 先尝试按 name 查询
        skill_obj = LLMSkill.objects.filter(name=skill_id, team__contains=int(team)).first()
        # 如果未找到，尝试按 instance_id 查询
        if not skill_obj:
            skill_obj = LLMSkill.objects.filter(instance_id=skill_id, team__contains=int(team)).first()
    else:
        # 先尝试按 name 查询
        skill_obj = LLMSkill.objects.filter(name=skill_id, bot=bot_id).first()
        # 如果未找到，尝试按 instance_id 查询
        if not skill_obj:
            skill_obj = LLMSkill.objects.filter(instance_id=skill_id, bot=bot_id).first()

    if not skill_obj:
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.skill_not_found", "No skill")}}]})
    messages = kwargs.get("messages")
    if not isinstance(messages, list) or not messages:
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.message_required", "Message is required")}}]})
    num = safe_conversation_window_size(kwargs, skill_obj.conversation_window_size)
    chat_history = [{"message": i.get("content", ""), "event": i.get("role", "")} for i in messages[-1 * num :] if isinstance(i, dict)]
    if not chat_history or not chat_history[-1]["message"]:
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.message_required", "Message is required")}}]})

    params = {
        "llm_model": skill_obj.llm_model_id,
        "skill_prompt": kwargs.get("prompt", "") or kwargs.get("skill_prompt", "") or skill_obj.skill_prompt,
        "temperature": pick_request_value(kwargs, "temperature", skill_obj.temperature),
        "chat_history": chat_history,
        "user_message": chat_history[-1]["message"],
        "conversation_window_size": num,
        "show_think": skill_obj.show_think,
        "tools": skill_obj.tools,
        "skill_type": skill_obj.skill_type,
        "group": skill_obj.team[0],
        "wiki_kb_ids": list(skill_obj.wiki_knowledge_bases.values_list("id", flat=True)),
    }

    return skill_obj, params, None


def invoke_chat(params, skill_obj, kwargs, current_ip, user_message, history_log=None):
    return_data, _, is_error = get_chat_msg(current_ip, kwargs, params, skill_obj, user_message, history_log)
    if is_error:
        return JsonResponse(return_data, status=500)
    return JsonResponse(return_data)


def format_knowledge_sources(content, skill_obj, doc_map=None, title_map=None):
    """知识库引用已移除，直接返回原始内容（保留签名以兼容调用方）。"""
    return content


def get_chat_msg(current_ip, kwargs, params, skill_obj, user_message, history_log=None):
    # 使用同步版本的 invoke_chat
    data, doc_map, title_map = ChatService.invoke_chat(params)

    # 检查执行是否失败
    if data.get("success") is False:
        error_response = {
            "error": {
                "message": data.get("error", data.get("message", "Unknown error")),
                "type": data.get("error_type", "ExecutionError"),
                "code": "execution_failed",
            }
        }
        return error_response, None, True  # 第三个返回值表示是否失败

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
    if history_log:
        history_log.conversation = content
        history_log.save()
    insert_skill_log(current_ip, skill_obj.id, return_data, kwargs, user_message=user_message)
    return return_data, content, False  # 第三个返回值表示是否失败


def _build_chat_completion_service() -> ChatCompletionService:
    """Wire the shared chat-completion service to the view-layer callables.

    The dependencies are resolved lazily via module-level names so existing
    test patches on ``apps.opspilot.views.*`` (e.g. ``validate_openai_token``,
    ``get_skill_and_params``, ``insert_skill_log``) remain authoritative.
    """
    return ChatCompletionService(
        parse_json_body=parse_json_body,
        extract_api_token=extract_api_token,
        get_client_ip=get_client_ip,
        generate_stream_error=generate_stream_error,
        insert_skill_log=insert_skill_log,
        invoke_chat=invoke_chat,
        stream_chat=stream_chat,
    )


@api_exempt
def openai_completions(request):
    """Main entry point for OpenAI completions"""
    service = _build_chat_completion_service()
    return service.run(
        request,
        validate=lambda token, kwargs: validate_openai_token(token),
        resolve_skill=lambda kwargs, user: get_skill_and_params(kwargs, user.team),
        get_user_id=lambda user: user.username,
    )


def _lobe_persist_history(params, skill_obj, user_message, user, kwargs):
    """Persist the inbound user turn and build the bot-side history log.

    Mirrors the legacy ``lobe_skill_execute`` side effects exactly: it creates a
    ``user`` conversation row and returns an unsaved ``bot`` conversation row to
    be filled in once the assistant response is produced.
    """
    bot = Bot.objects.get(id=kwargs["studio_id"])
    BotConversationHistory.objects.create(
        bot_id=kwargs.get("studio_id"),
        channel_user_id=user["username"],
        created_by=bot.created_by,
        domain=bot.domain,
        conversation_role="user",
        conversation=user_message,
    )
    return BotConversationHistory(
        bot_id=kwargs.get("studio_id"),
        channel_user_id=user["username"],
        created_by=bot.created_by,
        domain=bot.domain,
        conversation_role="bot",
        conversation="",
    )


@api_exempt
def lobe_skill_execute(request):
    service = _build_chat_completion_service()
    return service.run(
        request,
        validate=lambda token, kwargs: validate_header_token(token, int(kwargs["studio_id"])),
        resolve_skill=lambda kwargs, user: get_skill_and_params(kwargs, "", kwargs.get("studio_id")),
        get_user_id=lambda user: user["username"],
        post_resolve_hook=_lobe_persist_history,
    )


@api_exempt
def skill_execute(request):
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse(
            {"choices": [{"message": {"role": "assistant", "content": parse_error}}]},
            status=400,
        )
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
    loader = get_loader(request)
    api_token = extract_api_token(request)
    if not api_token:
        return {"content": loader.get("error.no_authorization", "No authorization")}
    bot = Bot.objects.filter(id=bot_id, api_token=api_token).first()
    if not bot:
        logger.info(f"Bot not found for bot_id: {bot_id}")
        return {"content": loader.get("error.bot_not_found", "No bot found")}
    try:
        result = SkillExecuteService.execute_skill(bot, skill_id, user_message, chat_history, sender_id, channel)
    except Exception:
        logger.exception("Skill execution failed: bot_id=%s, skill_id=%s", bot_id, skill_id)
        result = {"content": "Skill execution error"}
    if getattr(request, "api_pass", False):
        current_ip, _ = get_client_ip(request)
        insert_skill_log(
            current_ip,
            bot.llm_skills.first().id,
            result,
            kwargs,
            user_message=user_message,
        )
    return result


def _extract_token_usage(response_detail: Any) -> tuple[int, int, int]:
    """从 SkillRequestLog.response_detail 中解析 OpenAI 风格的 usage 字段。

    返回 (input_tokens, output_tokens, total_tokens)。
    """
    if not isinstance(response_detail, dict):
        return 0, 0, 0
    usage = response_detail.get("usage")
    if not isinstance(usage, dict):
        return 0, 0, 0

    def _to_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    prompt = _to_int(usage.get("prompt_tokens"))
    completion = _to_int(usage.get("completion_tokens"))
    total = _to_int(usage.get("total_tokens")) or (prompt + completion)
    return prompt, completion, total


def _user_team_ids(request) -> set[int]:
    """返回调用者可访问的团队 id 集合(superuser 返回空集表示不限制)。"""
    if getattr(request.user, "is_superuser", False):
        return set()
    return {g["id"] for g in getattr(request.user, "group_list", []) if isinstance(g, dict) and "id" in g}


def _bot_in_user_team(request, bot_id) -> bool:
    """校验 bot 属于调用者所在团队(superuser 不限制)。"""
    bot = Bot.objects.filter(id=bot_id).first()
    if not bot:
        return False
    if getattr(request.user, "is_superuser", False):
        return True
    team_ids = _user_team_ids(request)
    return bool(set(bot.team or []) & team_ids)


def _token_consumption_queryset(request):
    """按 bot_id(经由其关联技能)与时间范围过滤 SkillRequestLog。

    bot_id 必须属于调用者所在团队，否则返回空 queryset(配合 scope 校验)。
    """
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = set_time_range(end_time_str, start_time_str)
    queryset = SkillRequestLog.objects.filter(created_at__range=[start_time, end_time], state=True)
    bot_id = request.GET.get("bot_id")
    if bot_id:
        if not _bot_in_user_team(request, bot_id):
            return queryset.none(), start_time, end_time
        skill_ids = LLMSkill.objects.filter(bot__id=bot_id).values_list("id", flat=True)
        queryset = queryset.filter(skill_id__in=skill_ids)
    return queryset, start_time, end_time


@HasRole("admin")
def get_total_token_consumption(request):
    queryset, _start_time, _end_time = _token_consumption_queryset(request)
    input_tokens = output_tokens = total_tokens = 0
    for response_detail in queryset.values_list("response_detail", flat=True).iterator():
        prompt, completion, total = _extract_token_usage(response_detail)
        input_tokens += prompt
        output_tokens += completion
        total_tokens += total
    data = {
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_token_consumption_overview(request):
    queryset, start_time, end_time = _token_consumption_queryset(request)
    num_days = (end_time - start_time).days + 1
    daily_totals = {(start_time + datetime.timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(num_days)}
    for created_at, response_detail in queryset.values_list("created_at", "response_detail").iterator():
        _prompt, _completion, total = _extract_token_usage(response_detail)
        date_key = created_at.strftime("%Y-%m-%d")
        if date_key not in daily_totals:
            daily_totals[date_key] = 0
        daily_totals[date_key] += total
    items = [{"date": date, "tokens": tokens} for date, tokens in sorted(daily_totals.items())]
    return JsonResponse({"result": True, "data": {"items": items}})


@HasRole("admin")
def get_conversations_line_data(request):
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = set_time_range(end_time_str, start_time_str)
    bot_id = request.GET.get("bot_id")
    if bot_id and not _bot_in_user_team(request, bot_id):
        return JsonResponse({"result": True, "data": set_channel_type_line(end_time, [], start_time)})
    queryset = (
        BotConversationHistory.objects.filter(
            created_at__range=[start_time, end_time],
            bot_id=bot_id,
            conversation_role="bot",
        )
        .annotate(date=TruncDate("created_at"))
        .values("channel_user__channel_type", "date")
        .annotate(count=Count("id"))  # 不去重，按记录统计
    )
    # 生成日期范围内的所有日期
    result = set_channel_type_line(end_time, queryset, start_time)
    return JsonResponse({"result": True, "data": result})


@HasRole("admin")
def get_active_users_line_data(request):
    start_time_str = request.GET.get("start_time")
    end_time_str = request.GET.get("end_time")
    end_time, start_time = set_time_range(end_time_str, start_time_str)
    bot_id = request.GET.get("bot_id")
    if bot_id and not _bot_in_user_team(request, bot_id):
        return JsonResponse({"result": True, "data": set_channel_type_line(end_time, [], start_time)})
    queryset = (
        BotConversationHistory.objects.filter(created_at__range=[start_time, end_time], bot_id=bot_id, conversation_role="user")
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
        if channel_type not in result_dict:
            result_dict[channel_type] = formatted_dates.copy()
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
async def execute_chat_flow(request, bot_id, node_id):
    """执行ChatFlow流程（支持流式响应）"""
    loader = await sync_to_async(get_loader, thread_sensitive=True)(request)
    if not bot_id or not node_id:
        return JsonResponse({"result": False, "message": loader.get("error.bot_node_id_required", "Bot ID and Node ID are required.")})

    # 读取请求体
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)
    message = kwargs.get("message", "") or kwargs.get("user_message", "")
    session_id = kwargs.get("session_id", "")
    is_test = kwargs.get("is_test", False)

    # 验证token
    token = extract_api_token(request)
    is_valid, msg = await sync_to_async(validate_openai_token, thread_sensitive=False)(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg)

    # 验证Bot — 始终按已验证用户所属团队作用域解析 bot，所有客户端一致
    # (此前移动端基于可伪造的 User-Agent 绕过 team 校验，构成跨租户越权，已移除)
    user = msg
    current_team = int(user.team)
    # 构建 team 过滤：
    # - 测试(is_test=True，管理页测试)：仅【管理组织】可发起。测试会回填管理画布、占用"同 bot
    #   同时仅一个测试"的槽位，属管理活动，使用组织不得触发(即便经 API)。
    # - 正常对话(is_test=False)：【使用组织】即可对话(管理组织因 team ⊆ usage_team 已被包含)，
    #   外加 OpsPilotGuest 顶级组(嵌入/访客对话，维持原行为)。
    if is_test:
        team_filter = Q(team__contains=[current_team])
    else:
        guest_group_ids = {
            int(group["id"])
            for group in getattr(user, "group_list", [])
            if isinstance(group, dict) and group.get("name") == "OpsPilotGuest" and group.get("id") is not None
        }
        team_filter = Q(usage_team__contains=[current_team])
        for gid in guest_group_ids:
            team_filter |= Q(team__contains=[gid])

    bot_query = Bot.objects.filter(Q(id=bot_id) & team_filter)
    if not is_test:
        bot_query = bot_query.filter(online=True)
    bot_obj = await sync_to_async(bot_query.first, thread_sensitive=False)()
    if not bot_obj:
        return JsonResponse({"result": False, "message": loader.get("error.bot_not_online", "No bot online")})

    # 获取Bot的工作流配置
    bot_chat_flow = await sync_to_async(BotWorkFlow.objects.filter(bot_id=bot_obj.id).first, thread_sensitive=False)()
    if not bot_chat_flow:
        return JsonResponse({"result": False, "message": loader.get("error.no_chat_flow_configured", "No chat flow configured for this bot.")})

    # 检查工作流是否有配置数据
    if not bot_chat_flow.flow_json:
        return JsonResponse({"result": False, "message": loader.get("error.chat_flow_config_empty", "Chat flow configuration is empty.")})

    try:
        # 会话级 pending 拦截：若该 (bot, session) 当前有正在等待用户输入的智能体节点，
        # 则把本条对话框消息当作答案直接投递回该节点（在原流续跑），不新建执行——
        # 否则消息会从工作流入口重跑，回复跑回第一个智能体而非正在等待的那个。
        if not is_test and session_id and message:
            delivered = await sync_to_async(try_deliver_to_pending, thread_sensitive=False)(bot_id, session_id, message)
            if delivered:
                logger.info(
                    f"[ChatFlow] 消息已投递给待回答节点，跳过新建执行 - bot_id: {bot_id}, session_id: {session_id}, "
                    f"execution_id: {delivered.get('execution_id')}, node_id: {delivered.get('node_id')}"
                )
                return JsonResponse({"result": True, "data": delivered})

        # 创建ChatFlow引擎 - 使用数据库中的工作流配置
        engine = create_chat_flow_engine(bot_chat_flow, node_id)

        # 获取当前节点类型并设置 entry_type
        node_obj = engine._get_node_by_id(node_id)
        node_type = node_obj.get("type") if node_obj else None
        engine.entry_type = node_type  # 设置入口类型

        # 准备输入数据
        input_data = {
            "last_message": message,
            "user_id": f"{user.username}@{user.domain}",
            "bot_id": bot_id,
            "node_id": node_id,
            "session_id": session_id,
            "execution_id": engine.execution_id,
            "locale": getattr(user, "locale", "en"),  # 用户语言设置，用于 browser-use 输出国际化
        }

        logger.info(f"开始执行ChatFlow流程，bot_id: {bot_id}, node_id: {node_id}, user: {user.username}, node_type: {node_type}")

        if is_test:
            has_running_test = await sync_to_async(
                WorkFlowTaskResult.objects.filter(bot_work_flow__bot_id=bot_obj.id, status=WorkFlowTaskStatus.RUNNING, is_test=True).exists,
                thread_sensitive=False,
            )()
            if has_running_test:
                msg = loader.get("error.chat_flow_test_running", "A workflow test execution is already running for this bot.")
                return JsonResponse({"result": False, "message": msg})

            execution_id = str(uuid.uuid4())
            input_data["entry_type"] = node_type
            input_data["execution_id"] = execution_id

            async_task = chat_flow_test_execute_task.delay(bot_chat_flow.id, node_id, input_data, node_type, execution_id)
            return JsonResponse({"result": True, "data": {"status": "accepted", "execution_id": execution_id, "task_id": async_task.id}})

        # 区分流式响应节点类型：openai、agui、embedded_chat、mobile、web_chat
        stream_node_types = ["openai", "agui", "embedded_chat", "mobile", "web_chat"]
        if node_type in stream_node_types:
            # 使用引擎的流式执行方法，设置入口类型
            input_data["entry_type"] = node_type

            # 直接返回 engine.sse_execute 的 StreamingHttpResponse（与 execute_agui 保持一致）
            logger.info(f"[ChatFlow] 调用流式执行 - bot_id: {bot_id}, node_id: {node_id}, node_type: {node_type}")
            return await sync_to_async(engine.sse_execute, thread_sensitive=False)(input_data)

        # 非流式节点，使用普通执行（在线程池中执行，不阻塞事件循环）
        result = await sync_to_async(engine.execute, thread_sensitive=False)(input_data)
        return JsonResponse({"result": True, "data": {"content": result, "execution_time": time.time()}})

    except Exception as e:
        logger.exception("ChatFlow execution failed: bot_id=%s, node_id=%s", bot_id, node_id)
        # 流式错误响应，参考 llm_view.py
        return create_error_stream_response(str(e))


def interrupt_chat_flow_execution(request):
    """按 execution_id 请求中断 ChatFlow 执行，仅供本地 server 内部场景使用。"""
    loader = get_loader(request)
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)

    serializer = InterruptChatFlowRequestSerializer(data=kwargs)
    if not serializer.is_valid():
        return JsonResponse({"result": False, "message": loader.get("error.execution_id_required", "execution_id is required")}, status=400)
    validated = serializer.validated_data
    execution_id = validated["execution_id"]

    token = extract_api_token(request)
    is_valid, msg = validate_openai_token(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg)
    user = msg

    # 将 execution_id 绑定到已验证 token 所属团队：仅当该执行实例归属于调用者团队的 bot 时才允许中断，
    # 否则拒绝（404），防止跨租户中断他人工作流执行。
    task_result = (
        WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            bot_work_flow__bot__team__contains=int(user.team),
        )
        .order_by("-id")
        .first()
    )
    if not task_result:
        return JsonResponse(
            {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
            status=404,
        )

    request_interrupt(execution_id, reason=validated["reason"])
    if task_result.status not in {WorkFlowTaskStatus.SUCCESS, WorkFlowTaskStatus.FAIL, WorkFlowTaskStatus.INTERRUPTED}:
        task_result.status = WorkFlowTaskStatus.INTERRUPTED
        task_result.finished_at = datetime.datetime.now(datetime.UTC)
        task_result.save(update_fields=["status", "finished_at"])

    return JsonResponse(
        {
            "result": True,
            "data": {
                "execution_id": execution_id,
                "status": WorkFlowTaskStatus.INTERRUPTED,
                "interrupt_requested": True,
            },
        }
    )


def submit_approval(request):
    """提交审批决策 — 用户对 Agent 危险操作的批准/拒绝。

    要求有效的 API Token（与 interrupt_chat_flow_execution 保持一致），并校验
    execution_id 归属于 Token 所属团队的 Bot，防止跨租户伪造审批决策。
    """
    loader = get_loader(request)
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)

    # 认证：要求有效 Token
    token = extract_api_token(request)
    is_valid, msg = validate_openai_token(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg, status=401)
    user = msg

    serializer = SubmitApprovalRequestSerializer(data=kwargs)
    if not serializer.is_valid():
        errors = serializer.errors
        if "decision" in errors and all(k not in errors for k in ("execution_id", "node_id", "tool_call_id")):
            message = "decision must be 'approve' or 'reject'"
        else:
            message = "execution_id, node_id, tool_call_id, decision are all required"
        return JsonResponse({"result": False, "message": message}, status=400)

    validated = serializer.validated_data
    execution_id = validated["execution_id"]
    node_id = validated["node_id"]
    tool_call_id = validated["tool_call_id"]
    decision = validated["decision"]

    # 归属校验：execution_id 必须属于调用者所在团队的 Bot
    task_result = (
        WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            bot_work_flow__bot__team__contains=int(user.team),
        )
        .order_by("-id")
        .first()
    )
    if not task_result:
        return JsonResponse(
            {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
            status=404,
        )

    from apps.opspilot.services.approval import submit_approval_decision

    submit_approval_decision(
        execution_id=execution_id,
        node_id=node_id,
        tool_call_id=tool_call_id,
        decision=decision,
        reason=validated["reason"],
        decided_by=kwargs.get("decided_by", getattr(user, "username", "")),
    )

    return JsonResponse({"result": True, "data": {"execution_id": execution_id, "node_id": node_id, "decision": decision}})


def submit_choice(request):
    """提交用户选择 — 用户从多个选项中选择的结果。

    要求有效的 API Token，并校验 execution_id 归属于 Token 所属团队的 Bot，
    防止攻击者劫持他人工作流的选项决策。
    """
    loader = get_loader(request)
    if request.method != "POST":
        return JsonResponse({"result": False, "message": "Method not allowed"}, status=405)

    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)

    # 认证：要求有效 Token
    token = extract_api_token(request)
    is_valid, msg = validate_openai_token(token, get_current_team(request) or None)
    if not is_valid:
        return JsonResponse(msg, status=401)
    user = msg

    serializer = SubmitChoiceRequestSerializer(data=kwargs)
    if not serializer.is_valid():
        errors = serializer.errors
        if "selected" in errors and all(k not in errors for k in ("execution_id", "node_id", "choice_id")):
            message = "selected must be a non-empty list"
        else:
            message = "execution_id, node_id, choice_id are all required"
        return JsonResponse({"result": False, "message": message}, status=400)

    validated = serializer.validated_data
    execution_id = validated["execution_id"]
    node_id = validated["node_id"]
    choice_id = validated["choice_id"]
    selected = validated["selected"]

    # 归属校验：execution_id 必须属于调用者所在团队的 Bot
    task_result = (
        WorkFlowTaskResult.objects.filter(
            execution_id=execution_id,
            bot_work_flow__bot__team__contains=int(user.team),
        )
        .order_by("-id")
        .first()
    )
    if not task_result:
        if node_id != "skill_test":
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        logger.warning(
            "Local skill test choice submitted without workflow task result: execution_id=%s, choice_id=%s",
            execution_id,
            choice_id,
        )

    from apps.opspilot.utils.user_choice import submit_user_choice

    submit_user_choice(
        execution_id=execution_id,
        node_id=node_id,
        choice_id=choice_id,
        selected=selected,
    )

    return JsonResponse({"result": True, "data": {"execution_id": execution_id, "node_id": node_id, "selected": selected}})


@api_exempt
def execute_chat_flow_wechat_official(request, bot_id):
    """微信公众号ChatFlow执行入口

    通过微信公众号发送消息，调用指定的ChatFlow进行流程节点执行并返回数据
    """
    # 1. 验证Bot ID
    if not bot_id:
        logger.error("微信公众号ChatFlow执行失败：缺少Bot ID")
        return HttpResponse("success")

    # 2. 创建工具类实例并验证Bot和工作流配置
    wechat_official_utils = WechatOfficialChatFlowUtils(bot_id)
    bot_chat_flow, error_response = wechat_official_utils.validate_bot_and_workflow()
    if error_response:
        return error_response

    # 3. 获取微信公众号节点配置
    wechat_config, error_response = wechat_official_utils.get_wechat_official_node_config(bot_chat_flow)
    if error_response:
        return error_response

    # 4. 处理GET请求（URL验证）
    if request.method == "GET":
        return wechat_official_utils.handle_url_verification(
            request.GET.get("signature", "") or request.GET.get("msg_signature", ""),
            request.GET.get("timestamp", ""),
            request.GET.get("nonce", ""),
            request.GET.get("echostr", ""),
            wechat_config["token"],
            wechat_config["aes_key"],
            wechat_config["appid"],
        )

    # 5. 处理POST请求（消息处理）
    return wechat_official_utils.handle_wechat_message(request, wechat_config, bot_chat_flow)


@api_exempt
def execute_chat_flow_wechat(request, bot_id):
    """企业微信ChatFlow执行入口

    通过企业微信发送消息，调用指定的ChatFlow进行流程节点执行并返回数据
    """
    # 1. 验证Bot ID
    if not bot_id:
        logger.error("企业微信ChatFlow执行失败：缺少Bot ID")
        return HttpResponse("success")

    # 2. 创建工具类实例并验证Bot和工作流配置
    wechat_utils = WechatChatFlowUtils(bot_id)
    bot_chat_flow, error_response = wechat_utils.validate_bot_and_workflow()
    if error_response:
        return error_response

    # 3. 获取企业微信节点配置
    wechat_config, error_response = wechat_utils.get_wechat_node_config(bot_chat_flow)
    if error_response:
        return error_response

    # 4. 创建加密对象
    try:
        crypto = WeChatCrypto(wechat_config["token"], wechat_config["aes_key"], wechat_config["corp_id"])
    except Exception:
        logger.exception("企业微信ChatFlow执行失败：创建加密对象失败")
        return HttpResponse("success")

    # 5. 处理GET请求（URL验证）
    if request.method == "GET":
        return wechat_utils.handle_url_verification(
            crypto,
            request.GET.get("signature", "") or request.GET.get("msg_signature", ""),
            request.GET.get("timestamp", ""),
            request.GET.get("nonce", ""),
            request.GET.get("echostr", ""),
        )

    # 6. 处理POST请求（消息处理）
    return wechat_utils.handle_wechat_message(request, crypto, bot_chat_flow, wechat_config)


@api_exempt
def execute_chat_flow_dingtalk(request, bot_id):
    """钉钉ChatFlow执行入口

    支持两种模式：
    1. HTTP回调模式：处理来自钉钉服务器的POST请求
    2. Stream模式（长连接）：启动并返回状态检查接口

    GET请求返回状态，POST请求处理消息
    特殊操作：
    - POST /dingtalk/{bot_id}/stream/start - 启动Stream客户端
    """
    loader = get_loader(request)

    # 处理GET请求 - 健康检查/状态查询
    if request.method == "GET":
        return JsonResponse({"status": "ok", "bot_id": bot_id})

    # 1. 验证Bot ID
    if not bot_id:
        logger.error("钉钉ChatFlow执行失败：缺少Bot ID")
        return JsonResponse({"success": False, "message": loader.get("error.missing_bot_id", "Missing bot_id")})

    # 2. 创建工具类实例并验证Bot和工作流配置
    dingtalk_utils = DingTalkChatFlowUtils(bot_id)
    bot_chat_flow, error_response = dingtalk_utils.validate_bot_and_workflow()
    if error_response:
        return error_response

    # 3. 获取钉钉节点配置
    dingtalk_config, error_response = dingtalk_utils.get_dingtalk_node_config(bot_chat_flow)
    if error_response:
        return error_response

    # 4. 检查是否是Stream模式启动请求
    try:
        data = json.loads(request.body) if request.body else {}
        if data.get("action") == "start_stream":
            # 启动Stream客户端
            success = start_dingtalk_stream_client(bot_id, bot_chat_flow, dingtalk_config)
            if success:
                return JsonResponse({"success": True, "message": "DingTalk Stream client started successfully", "mode": "stream"})
            else:
                return JsonResponse({"success": False, "message": "Failed to start DingTalk Stream client", "mode": "stream"})
    except json.JSONDecodeError:
        pass

    # 5. 处理HTTP回调模式的消息
    return dingtalk_utils.handle_dingtalk_message(request, bot_chat_flow, dingtalk_config)
