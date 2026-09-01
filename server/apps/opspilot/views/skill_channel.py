import json
from types import SimpleNamespace

from django.http import HttpResponse, JsonResponse

from apps.core.utils.exempt import api_exempt
from apps.core.utils.team_utils import get_current_team
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY, CallerIdentityError, capture_caller_identity, mark_api_secret_identity
from apps.opspilot.services.session_context_usage import summarize_skill_session_usage
from apps.opspilot.services.skill_channel_chat_service import (
    EMBEDDED,
    PLATFORM_OR_WEB,
    SkillChannelChatError,
    assert_org_access,
    authenticate_embedded,
    build_skill_chat_params,
    delete_skill_session,
    get_enabled_channel,
    get_skill_session_history,
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
from apps.opspilot.utils.agui_chat import stream_agui_chat
from apps.opspilot.utils.sse_chat import create_error_stream_response
from apps.opspilot.views.chat_flow import parse_json_body


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
            "enable_conversation_history": bool(getattr(ch.skill, "enable_conversation_history", False)),
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
            "enable_conversation_history": bool(getattr(skill, "enable_conversation_history", False)),
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
        messages, conversation = get_skill_session_history(session_id=session_id, external_user_id=saas_external_user_id(request.user))
    except SkillChannelChatError as e:
        return JsonResponse({"result": False, "message": e.message}, status=e.status)
    return JsonResponse(
        {
            "result": True,
            "data": {
                "messages": messages,
                "llm_context_usage": summarize_skill_session_usage(conversation),
            },
        }
    )


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

    channel = SkillChannel.objects.filter(id=channel_id, channel_type=channel_type).first()
    if not channel or not channel.enabled:
        if request.method == "GET":
            return HttpResponse("fail", status=403)
        return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

    if request.method == "GET":
        return HttpResponse("success")

    return JsonResponse({"result": False, "message": f"不支持的渠道类型: {channel_type}"}, status=400)
