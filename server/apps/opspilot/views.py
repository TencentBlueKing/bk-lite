import datetime
import json
import time
import uuid
from types import SimpleNamespace
from typing import Any

from asgiref.sync import sync_to_async
from django.core import signing
from django.db.models import Q
from django.http import FileResponse, HttpResponse, JsonResponse
from ipware import get_client_ip
from wechatpy.enterprise import WeChatCrypto

from apps.base.models import UserAPISecret
from apps.core.decorators.api_permission import HasRole
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.exempt import api_exempt
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.enum import SkillChannelChoices, WorkFlowTaskStatus
from apps.opspilot.models import Bot, BotChannel, BotWebChatSession, BotWorkFlow, LLMSkill, WorkFlowTaskResult
from apps.opspilot.serializers.request_serializers import (
    InterruptChatFlowRequestSerializer,
    SubmitApprovalRequestSerializer,
    SubmitChoiceRequestSerializer,
)
from apps.opspilot.services import usage_statistics_service
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY, CallerIdentityError, capture_caller_identity, mark_api_secret_identity
from apps.opspilot.services.chat_completion_service import ChatCompletionService
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils, start_dingtalk_stream_client
from apps.opspilot.services.skill_channel_chat_service import (
    EMBEDDED,
    PLATFORM_OR_WEB,
    SkillChannelChatError,
    assert_org_access,
    authenticate_embedded,
    build_skill_chat_params,
    delete_skill_session,
    get_enabled_channel,
    get_skill_session_messages,
    list_skill_conversations_for_user,
    normalize_client_chat_history,
    saas_external_user_id,
    split_user_message_and_history,
    stream_skill_channel_chat,
    truncate_chat_history,
)
from apps.opspilot.services.skill_channel_service import (
    platform_channels_for_team,
    published_web_channel_for_skill,
    published_web_skills_for_team,
    web_chat_channels_for_team,
)
from apps.opspilot.services.skill_execute_service import SkillExecuteService
from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils
from apps.opspilot.services.workflow_attachment_service import resolve_signed_attachment_token
from apps.opspilot.tasks import chat_flow_test_execute_task
from apps.opspilot.utils.agui_chat import stream_agui_chat
from apps.opspilot.utils.bot_utils import insert_skill_log, set_time_range
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.execution_interrupt import request_interrupt
from apps.opspilot.utils.pending_hitl import try_deliver_to_pending
from apps.opspilot.utils.sse_chat import create_error_stream_response, generate_stream_error, stream_chat
from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import User

# 智能体 / AGUI 本地会话没有 WorkFlowTaskResult；与 request_user_choice 默认 node_id 对齐。
LOCAL_SKILL_HITL_NODES = frozenset({"skill_test", "deep_agent"})


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
    bot = Bot.objects.filter(id=bot_id, api_token=api_token).first()  # pragma: no cover
    if not bot:  # pragma: no cover
        return JsonResponse({})
    channels = BotChannel.objects.filter(bot_id=bot_id, enabled=True)  # pragma: no cover
    return_data = {  # pragma: no cover
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
    return JsonResponse(return_data)  # pragma: no cover


@api_exempt
def download_workflow_attachment(request, download_token):  # pragma: no cover
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
    token = token.split("Bearer ")[-1]  # pragma: no cover
    user = UserAPISecret.find_by_api_secret(token)  # pragma: no cover
    if not user:  # pragma: no cover
        if team is None and not is_mobile:
            return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
        team = team or 0  # pragma: no cover
        client = SystemMgmt()  # pragma: no cover
        result = client.verify_token(token)  # pragma: no cover
        if not result.get("result"):  # pragma: no cover
            return False, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.no_authorization", "No authorization")}}]}
        user_info = result.get("data")  # pragma: no cover
        # JWT/session identity must not be a UserAPISecret instance: capture_caller_identity
        # treats that model as API-secret scope (bound team, no include_children cookie).
        user = SimpleNamespace(  # pragma: no cover
            username=user_info["username"],
            domain=user_info["domain"],
            team=int(team),
            locale=user_info.get("locale", "en"),
            group_list=user_info.get("group_list", []),
            is_authenticated=True,
        )
    else:
        # UserAPISecret 认证：查询用户信息获取 locale
        mark_api_secret_identity(user)
        user.locale = _get_user_locale(user.username, user.domain)  # pragma: no cover
    return True, user  # pragma: no cover


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
        user_obj = User.objects.filter(username=username, domain=domain).first()  # pragma: no cover
        if user_obj:  # pragma: no cover
            return user_obj.locale or "en"
    except Exception as e:
        logger.warning(f"Failed to get user locale for {username}@{domain}: {e}")  # pragma: no cover
    return "en"


def get_skill_and_params(kwargs, team, bot_id=None):
    """Get skill object and prepare parameters for LLM invocation

    支持通过 name 或 instance_id 查询 skill
    """
    loader = LanguageLoader(app="opspilot", default_lang="en")
    skill_id = kwargs.get("model")
    if not skill_id:
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.skill_not_found", "No skill")}}]})

    # 尝试通过 name 或 instance_id 查询
    if not bot_id:  # pragma: no cover
        # 先尝试按 name 查询
        skill_obj = LLMSkill.objects.filter(name=skill_id, team__contains=int(team)).first()
        # 如果未找到，尝试按 instance_id 查询
        if not skill_obj:
            skill_obj = LLMSkill.objects.filter(instance_id=skill_id, team__contains=int(team)).first()
    else:  # pragma: no cover
        # 先尝试按 name 查询
        skill_obj = LLMSkill.objects.filter(name=skill_id, bot=bot_id).first()
        # 如果未找到，尝试按 instance_id 查询
        if not skill_obj:
            skill_obj = LLMSkill.objects.filter(instance_id=skill_id, bot=bot_id).first()

    if not skill_obj:  # pragma: no cover
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.skill_not_found", "No skill")}}]})
    messages = kwargs.get("messages")  # pragma: no cover
    if not isinstance(messages, list) or not messages:  # pragma: no cover
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.message_required", "Message is required")}}]})
    num = safe_conversation_window_size(kwargs, skill_obj.conversation_window_size)  # pragma: no cover
    chat_history = [
        {"message": i.get("content", ""), "event": i.get("role", "")} for i in messages[-1 * num :] if isinstance(i, dict)
    ]  # pragma: no cover
    if not chat_history or not chat_history[-1]["message"]:  # pragma: no cover
        return (None, None, {"choices": [{"message": {"role": "assistant", "content": loader.get("error.message_required", "Message is required")}}]})

    params = {  # pragma: no cover
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

    return skill_obj, params, None  # pragma: no cover


def invoke_chat(params, skill_obj, kwargs, current_ip, user_message, history_log=None):  # pragma: no cover
    return_data, _, is_error = get_chat_msg(current_ip, kwargs, params, skill_obj, user_message, history_log)
    if is_error:
        return JsonResponse(return_data, status=500)
    return JsonResponse(return_data)


def format_knowledge_sources(content, skill_obj, doc_map=None, title_map=None):  # pragma: no cover
    """知识库引用已移除，直接返回原始内容（保留签名以兼容调用方）。"""
    return content


def get_chat_msg(current_ip, kwargs, params, skill_obj, user_message, history_log=None):  # pragma: no cover
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


def _build_chat_completion_service() -> ChatCompletionService:  # pragma: no cover
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


def _enrich_openai_params(request, user, params):  # pragma: no cover
    params[CALLER_IDENTITY_CONFIG_KEY] = capture_caller_identity(request, user)


@api_exempt
def openai_completions(request):  # pragma: no cover
    """Main entry point for OpenAI completions"""
    service = _build_chat_completion_service()
    return service.run(
        request,
        validate=lambda token, kwargs: validate_openai_token(token),
        resolve_skill=lambda kwargs, user: get_skill_and_params(kwargs, user.team),
        get_user_id=lambda user: user.username,
        enrich_params=_enrich_openai_params,
    )


@api_exempt
def skill_execute(request):  # pragma: no cover
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


def get_skill_execute_result(bot_id, channel, chat_history, kwargs, request, sender_id, skill_id, user_message):  # pragma: no cover
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


_extract_token_usage = usage_statistics_service.extract_token_usage
_user_team_ids = usage_statistics_service.user_team_ids
_annotate_token_fields = usage_statistics_service.annotate_token_fields
set_channel_type_line = usage_statistics_service.format_channel_type_line


def _bot_in_user_team(request, bot_id) -> bool:
    """兼容旧导入/patch 点，团队作用域逻辑由统计 service 承载。"""
    return usage_statistics_service.bot_in_user_team(
        request,
        bot_id,
        team_ids_getter=_user_team_ids,
    )


def _token_consumption_queryset(request):  # pragma: no cover
    """兼容旧 patch 点，查询构造由统计 service 承载。"""
    return usage_statistics_service.token_consumption_queryset(
        request,
        bot_scope_check=_bot_in_user_team,
        time_range_getter=set_time_range,
    )


@HasRole("admin")
def get_total_token_consumption(request):  # pragma: no cover
    queryset, _start_time, _end_time = _token_consumption_queryset(request)
    data = usage_statistics_service.aggregate_token_totals(
        queryset,
        annotate=_annotate_token_fields,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_token_consumption_overview(request):  # pragma: no cover
    queryset, start_time, end_time = _token_consumption_queryset(request)
    data = usage_statistics_service.token_consumption_overview(
        queryset,
        start_time,
        end_time,
        annotate=_annotate_token_fields,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_conversations_line_data(request):  # pragma: no cover
    data = usage_statistics_service.conversation_line_data(
        request,
        role="bot",
        distinct_users=False,
        bot_scope_check=_bot_in_user_team,
        line_formatter=set_channel_type_line,
        time_range_getter=set_time_range,
    )
    return JsonResponse({"result": True, "data": data})


@HasRole("admin")
def get_active_users_line_data(request):  # pragma: no cover
    data = usage_statistics_service.conversation_line_data(
        request,
        role="user",
        distinct_users=True,
        bot_scope_check=_bot_in_user_team,
        line_formatter=set_channel_type_line,
        time_range_getter=set_time_range,
    )
    return JsonResponse({"result": True, "data": data})


@api_exempt
async def execute_chat_flow(request, bot_id, node_id):  # pragma: no cover
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
    try:
        caller_snapshot = capture_caller_identity(request, user)
    except CallerIdentityError as e:
        return JsonResponse({"result": False, "message": str(e)}, status=e.status_code)
    current_team = caller_snapshot["team_id"]
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
            # NATS 暴露会话参与者授权：当前用户必须为 BotWebChatSession 干系人之一
            web_session = await sync_to_async(
                BotWebChatSession.objects.filter(session_id=session_id).first,
                thread_sensitive=False,
            )()
            if web_session is not None and not web_session.is_participant(user):
                return JsonResponse({"result": False, "message": loader.get("error.session_not_participant", "当前用户不在该会话的干系人列表中")}, status=403)

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
            CALLER_IDENTITY_CONFIG_KEY: caller_snapshot,
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


def interrupt_chat_flow_execution(request):  # pragma: no cover
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
        if WorkFlowTaskResult.objects.filter(execution_id=execution_id).exists():
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        request_interrupt(execution_id, reason=validated["reason"])
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


def submit_approval(request):  # pragma: no cover
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
        if node_id not in LOCAL_SKILL_HITL_NODES or WorkFlowTaskResult.objects.filter(execution_id=execution_id).exists():
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        logger.warning(
            "Local skill/AGUI approval submitted without workflow task result: execution_id=%s, node_id=%s, tool_call_id=%s",
            execution_id,
            node_id,
            tool_call_id,
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


def submit_choice(request):  # pragma: no cover
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
        # 技能调试 / AGUI DeepAgent 本地会话没有 WorkFlowTaskResult；
        # 与 request_user_choice、ask_limit_continue 默认 node_id 对齐后放行。
        if node_id not in LOCAL_SKILL_HITL_NODES:
            return JsonResponse(
                {"result": False, "message": loader.get("error.execution_not_found", "Execution not found")},
                status=404,
            )
        logger.warning(
            "Local skill/AGUI choice submitted without workflow task result: execution_id=%s, node_id=%s, choice_id=%s",
            execution_id,
            node_id,
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
def execute_chat_flow_wechat_official(request, bot_id):  # pragma: no cover
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
def execute_chat_flow_wechat(request, bot_id):  # pragma: no cover
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


@api_exempt  # pragma: no cover
def execute_chat_flow_enterprise_wechat_aibot(request, bot_id):  # pragma: no cover
    """企微智能机器人短连接 ChatFlow 执行入口。"""
    return EnterpriseWechatAibotChatFlowUtils(bot_id).handle_request(request)


@api_exempt
def execute_chat_flow_dingtalk(request, bot_id):  # pragma: no cover
    """钉钉ChatFlow执行入口

    支持两种模式：
    1. HTTP回调模式：处理来自钉钉服务器的POST请求
    2. Stream模式（长连接）：启动并返回状态检查接口

    GET请求返回状态，POST请求处理消息
    特殊操作：
    - POST /dingtalk/{bot_id}/stream/start - 启动Stream客户端
    """
    loader = get_loader(request)  # pragma: no cover

    # 处理GET请求 - 健康检查/状态查询
    if request.method == "GET":  # pragma: no cover
        return JsonResponse({"status": "ok", "bot_id": bot_id})

    # 1. 验证Bot ID
    if not bot_id:  # pragma: no cover
        logger.error("钉钉ChatFlow执行失败：缺少Bot ID")
        return JsonResponse({"success": False, "message": loader.get("error.missing_bot_id", "Missing bot_id")})

    # 2. 创建工具类实例并验证Bot和工作流配置
    dingtalk_utils = DingTalkChatFlowUtils(bot_id)  # pragma: no cover
    bot_chat_flow, error_response = dingtalk_utils.validate_bot_and_workflow()  # pragma: no cover
    if error_response:  # pragma: no cover
        return error_response

    # 3. 获取钉钉节点配置
    dingtalk_config, error_response = dingtalk_utils.get_dingtalk_node_config(bot_chat_flow)  # pragma: no cover
    if error_response:  # pragma: no cover
        return error_response

    # 4. 检查是否是Stream模式启动请求
    try:  # pragma: no cover
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
    return dingtalk_utils.handle_dingtalk_message(request, bot_chat_flow, dingtalk_config)  # pragma: no cover


def _serialize_saas_skill_channels(qs):
    return [
        {
            "id": ch.id,
            "skill_id": ch.skill_id,
            "skill_name": ch.skill.name if ch.skill_id else "",
            "name": ch.name or (ch.skill.name if ch.skill_id else ""),
            "channel_type": ch.channel_type,
            "introduction": getattr(ch.skill, "introduction", "") or "",
            "app_name": ch.name or (ch.skill.name if ch.skill_id else ""),
            "app_description": getattr(ch.skill, "introduction", "") or "",
        }
        for ch in qs
    ]


def list_platform_skill_channels(request):
    """当前用户有权限的已启用平台渠道列表（供悬浮壳等消费）。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"result": False, "message": "未登录"}, status=401)
    current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
    group_list = getattr(request.user, "group_list", None) or []
    qs = platform_channels_for_team(current_team, group_list)
    return JsonResponse({"result": True, "data": _serialize_saas_skill_channels(qs)})


def list_web_chat_skill_channels(request):
    """当前用户有权限的已启用 Web 对话渠道列表（供独立对话页消费）。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"result": False, "message": "未登录"}, status=401)
    current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
    group_list = getattr(request.user, "group_list", None) or []
    qs = web_chat_channels_for_team(current_team, group_list)
    return JsonResponse({"result": True, "data": _serialize_saas_skill_channels(qs)})


def _serialize_published_web_skills(skills):
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "introduction": getattr(skill, "introduction", "") or "",
            "conversation_window_size": skill.conversation_window_size,
        }
        for skill in skills
    ]


def list_published_web_skills(request):
    """当前组可用的已发布 Web 智能体列表（按 skill_id，使用组包含当前组）。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"result": False, "message": "未登录"}, status=401)
    current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
    group_list = getattr(request.user, "group_list", None) or []
    skills = published_web_skills_for_team(current_team, group_list)
    return JsonResponse({"result": True, "data": _serialize_published_web_skills(skills)})


def execute_published_web_skill_chat(request, skill_id):
    """已发布 Web 智能体 AGUI 流式对话：只传 skill_id 与对话历史，参数与窗口由服务端读取并截断。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return create_error_stream_response("未登录")
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return create_error_stream_response(parse_error)
    current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
    group_list = getattr(request.user, "group_list", None) or []
    try:
        channel = published_web_channel_for_skill(skill_id, current_team, group_list)
        if not channel:
            raise SkillChannelChatError("当前组织无权使用该智能体或未发布 Web 渠道", status=403)
        skill = channel.skill
        history = normalize_client_chat_history((kwargs or {}).get("chat_history"))
        user_message, history = split_user_message_and_history(
            (kwargs or {}).get("user_message") or (kwargs or {}).get("message"),
            history,
        )
        window = skill.conversation_window_size or 10
        history = truncate_chat_history(history, window)
        params = build_skill_chat_params(skill, user_message, request.user)
        params["chat_history"] = history
        params["conversation_window_size"] = window
        params["browser_use_force_task"] = True
        params[CALLER_IDENTITY_CONFIG_KEY] = capture_caller_identity(request, request.user)
    except SkillChannelChatError as e:
        return create_error_stream_response(e.message)
    except CallerIdentityError as e:
        return create_error_stream_response(str(e))

    current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if current_ip:
        current_ip = current_ip.split(",")[0].strip()
    else:
        current_ip = request.META.get("REMOTE_ADDR", "")
    return stream_agui_chat(params, skill.name, {}, current_ip, user_message, skill_id=skill.id)


def _require_login_and_web_channel(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return None, JsonResponse({"result": False, "message": "未登录"}, status=401)
    channel_id = request.GET.get("channel_id")
    if not channel_id:
        return None, JsonResponse({"result": False, "message": "channel_id 必填"}, status=400)
    try:
        channel = get_enabled_channel(int(channel_id), PLATFORM_OR_WEB)
        current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
        assert_org_access(channel, current_team, getattr(request.user, "group_list", None))
    except (TypeError, ValueError):
        return None, JsonResponse({"result": False, "message": "channel_id 无效"}, status=400)
    except SkillChannelChatError as e:
        return None, JsonResponse({"result": False, "message": e.message}, status=e.status)
    return channel, None


def list_skill_channel_conversations(request):
    """当前用户在该智能体下的会话列表（含各通道，供 Web 对话页历史）。"""
    channel, error = _require_login_and_web_channel(request)
    if error:
        return error
    data = list_skill_conversations_for_user(
        skill_id=channel.skill_id,
        external_user_id=saas_external_user_id(request.user),
    )
    return JsonResponse({"result": True, "data": data})


def list_skill_channel_session_messages(request):
    """当前用户指定会话的消息列表。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"result": False, "message": "未登录"}, status=401)
    session_id = request.GET.get("session_id") or ""
    if not session_id:
        return JsonResponse({"result": False, "message": "session_id 必填"}, status=400)
    try:
        data = get_skill_session_messages(session_id=session_id, external_user_id=saas_external_user_id(request.user))
    except SkillChannelChatError as e:
        return JsonResponse({"result": False, "message": e.message}, status=e.status)
    return JsonResponse({"result": True, "data": data})


def delete_skill_channel_session(request):
    """删除当前用户的一条智能体会话（级联消息）。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"result": False, "message": "未登录"}, status=401)
    session_id = ""
    try:
        body = json.loads(request.body.decode("utf-8") or "{}") if request.body else {}
        session_id = body.get("session_id") or request.POST.get("session_id") or ""
    except Exception:
        session_id = request.POST.get("session_id") or ""
    if not session_id:
        return JsonResponse({"result": False, "message": "session_id 必填"}, status=400)
    try:
        delete_skill_session(session_id=session_id, external_user_id=saas_external_user_id(request.user))
    except SkillChannelChatError as e:
        return JsonResponse({"result": False, "message": e.message}, status=e.status)
    return JsonResponse({"result": True})


def execute_skill_channel_chat(request, channel_id):
    """平台 / Web 登录态 SSE 对话（channel_type 须为 platform 或 web_chat）。"""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return create_error_stream_response("未登录")
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return create_error_stream_response(parse_error)
    message = kwargs.get("message", "") or kwargs.get("user_message", "")
    if not message:
        return create_error_stream_response("message 必填")
    session_id = kwargs.get("session_id") or ""
    page_context = kwargs.get("page_context")
    try:
        channel = get_enabled_channel(int(channel_id), PLATFORM_OR_WEB)
        current_team = request.COOKIES.get("current_team") or get_current_team(request) or "0"
        assert_org_access(channel, current_team, getattr(request.user, "group_list", None))
        external_user_id = saas_external_user_id(request.user)
        return stream_skill_channel_chat(
            channel=channel,
            user_message=message,
            request=request,
            external_user_id=external_user_id,
            session_id=session_id or None,
            page_context=page_context,
        )
    except SkillChannelChatError as e:
        return create_error_stream_response(e.message)


@api_exempt
def execute_skill_embedded_chat(request, skill_id, channel_id):
    """嵌入式对话：Api-Authorization + 固定 skill_id + channel_id。"""
    kwargs, parse_error = parse_json_body(request)
    if parse_error:
        return JsonResponse({"result": False, "message": parse_error}, status=400)
    message = (kwargs or {}).get("message", "") or (kwargs or {}).get("user_message", "")
    if not message:
        return create_error_stream_response("message 必填")
    session_id = (kwargs or {}).get("session_id") or ""
    try:
        user_secret, team_id = authenticate_embedded(request)
        channel = get_enabled_channel(int(channel_id), EMBEDDED)
        if int(channel.skill_id) != int(skill_id):
            raise SkillChannelChatError("skill_id 与渠道不匹配", status=400)
        assert_org_access(channel, team_id)
        # 构造可被 caller_identity 识别的用户对象
        user = SimpleNamespace(
            username=user_secret.username,
            domain=user_secret.domain,
            id=None,
            locale="zh-CN",
            is_authenticated=True,
        )
        mark_api_secret_identity(user)
        request.user = user
        request._api_current_team = team_id
        return stream_skill_channel_chat(
            channel=channel,
            user_message=message,
            request=request,
            external_user_id=f"{user_secret.username}@{user_secret.domain}",
            session_id=session_id or None,
            identity_user=user,
        )
    except SkillChannelChatError as e:
        return create_error_stream_response(e.message)


@api_exempt
def execute_skill_channel_im(request, channel_id, channel_type):
    """IM 回调入口：企微 aibot / 企微应用 / 公众号 / 钉钉 HTTP 已接完整协议。

    GET 用于 URL 校验；POST 在渠道未启用时拒绝。企微/钉钉/公众号不校验组织。
    """
    if channel_type == SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT:
        from apps.opspilot.services.skill_channel_aibot import SkillChannelAibotUtils

        return SkillChannelAibotUtils(channel_id).handle_request(request)

    if channel_type == SkillChannelChoices.ENTERPRISE_WECHAT:
        from apps.opspilot.services.skill_channel_wechat import SkillChannelWechatUtils

        return SkillChannelWechatUtils(channel_id).handle_request(request)

    if channel_type == SkillChannelChoices.WECHAT_OFFICIAL:
        from apps.opspilot.services.skill_channel_wechat_official import SkillChannelWechatOfficialUtils

        return SkillChannelWechatOfficialUtils(channel_id).handle_request(request)

    if channel_type == SkillChannelChoices.DINGTALK:
        from apps.opspilot.services.skill_channel_dingtalk import SkillChannelDingtalkUtils

        return SkillChannelDingtalkUtils(channel_id).handle_request(request)

    from apps.opspilot.models import SkillChannel

    channel = SkillChannel.objects.filter(id=channel_id, channel_type=channel_type).first()
    if not channel or not channel.enabled:
        if request.method == "GET":
            return HttpResponse("fail", status=403)
        return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

    if request.method == "GET":
        return HttpResponse("success")

    return JsonResponse({"result": False, "message": f"不支持的渠道类型: {channel_type}"}, status=400)
