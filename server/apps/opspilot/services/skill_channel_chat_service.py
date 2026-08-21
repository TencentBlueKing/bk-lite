"""智能体渠道对话：鉴权、会话持久化、SSE 执行。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

from apps.base.models import UserAPISecret
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SKILL_CHANNEL_SKIP_ORG_CHECK, SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY, CallerIdentityError, capture_caller_identity
from apps.opspilot.services.skill_channel_service import channel_allows_team, resolve_ops_pilot_guest_id
from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt, build_skill_package_strategy, hydrate_skill_packages
from apps.opspilot.utils.agui_chat import stream_agui_chat
from apps.opspilot.utils.prompt_utils import merge_skill_params
from apps.opspilot.utils.skill_execution_params import resolve_request_tools
from apps.opspilot.utils.sse_chat import create_error_stream_response


class SkillChannelChatError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_enabled_channel(channel_id: int, expected_types: set[str] | None = None) -> SkillChannel:
    try:
        channel = SkillChannel.objects.select_related("skill").get(id=channel_id)
    except SkillChannel.DoesNotExist as exc:
        raise SkillChannelChatError("渠道不存在", status=404) from exc
    if not channel.enabled:
        raise SkillChannelChatError("渠道已下线", status=403)
    if expected_types and channel.channel_type not in expected_types:
        raise SkillChannelChatError("渠道类型不匹配", status=400)
    return channel


def assert_org_access(channel: SkillChannel, team_id, group_list=None) -> None:
    if channel.channel_type in SKILL_CHANNEL_SKIP_ORG_CHECK:
        return
    if channel_allows_team(channel, team_id):
        return
    guest_id = resolve_ops_pilot_guest_id(group_list)
    if guest_id is not None and channel_allows_team(channel, guest_id):
        return
    raise SkillChannelChatError("当前组织无权使用该智能体渠道", status=403)


def authenticate_embedded(request) -> tuple[Any, int]:
    """Api-Authorization → UserAPISecret → (user-like, team)."""
    secret = request.META.get("HTTP_API_AUTHORIZATION") or request.headers.get("Api-Authorization")
    if not secret:
        raise SkillChannelChatError("缺少 Api-Authorization", status=401)
    user_secret = UserAPISecret.find_by_api_secret(secret)
    if not user_secret:
        raise SkillChannelChatError("无效的 API Secret", status=401)
    return user_secret, int(user_secret.team)


def saas_external_user_id(user) -> str:
    username = getattr(user, "username", "") or ""
    domain = getattr(user, "domain", "") or ""
    return f"{username}@{domain}" if domain else username


def get_or_create_conversation(channel: SkillChannel, external_user_id: str, session_id: str | None = None) -> SkillConversation:
    if session_id:
        conv = SkillConversation.objects.select_related("channel", "skill").filter(session_id=session_id).first()
        if conv:
            if (conv.external_user_id or "") != (external_user_id or ""):
                raise SkillChannelChatError("无权使用该会话", status=403)
            if conv.skill_id != channel.skill_id:
                raise SkillChannelChatError("会话与当前智能体不匹配", status=400)
            return conv
    return SkillConversation.objects.create(
        session_id=session_id or uuid.uuid4().hex,
        skill=channel.skill,
        channel=channel,
        external_user_id=external_user_id or "",
    )


def append_message(conversation: SkillConversation, role: str, content: str) -> SkillConversationMessage:
    msg = SkillConversationMessage.objects.create(conversation=conversation, role=role, content=content or "")
    if role == SkillConversationMessage.ROLE_USER and not (conversation.title or "").strip():
        text = (content or "").strip().replace("\n", " ")
        if text:
            conversation.title = f"{text[:50]}..." if len(text) > 50 else text
            conversation.save(update_fields=["title", "updated_at"])
    return msg


def conversation_display_title(conversation: SkillConversation) -> str:
    if (conversation.title or "").strip():
        return conversation.title.strip()
    first = conversation.messages.filter(role=SkillConversationMessage.ROLE_USER).order_by("created_at", "id").first()
    if not first or not (first.content or "").strip():
        return "新会话"
    text = first.content.strip().replace("\n", " ")
    return f"{text[:50]}..." if len(text) > 50 else text


def list_skill_conversations_for_user(*, skill_id: int, external_user_id: str) -> list[dict]:
    qs = (
        SkillConversation.objects.filter(skill_id=skill_id, external_user_id=external_user_id, is_active=True)
        .select_related("channel")
        .order_by("-updated_at", "-id")
    )
    result = []
    for conv in qs:
        channel = conv.channel
        result.append(
            {
                "session_id": conv.session_id,
                "title": conversation_display_title(conv),
                "skill_id": conv.skill_id,
                "channel_id": conv.channel_id,
                "channel_type": channel.channel_type if channel else "",
                "channel_name": (channel.name if channel else "") or "",
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if getattr(conv, "updated_at", None) else None,
            }
        )
    return result


def get_skill_session_messages(*, session_id: str, external_user_id: str) -> list[dict]:
    conv = SkillConversation.objects.filter(session_id=session_id, is_active=True).select_related("channel").first()
    if not conv:
        raise SkillChannelChatError("会话不存在", status=404)
    if (conv.external_user_id or "") != (external_user_id or ""):
        raise SkillChannelChatError("无权查看该会话", status=403)
    messages = []
    for msg in conv.messages.order_by("created_at", "id"):
        messages.append(
            {
                "id": msg.id,
                "conversation_role": msg.role,
                "conversation_content": msg.content,
                "conversation_time": msg.created_at.isoformat() if msg.created_at else None,
                "session_id": conv.session_id,
                "channel_type": conv.channel.channel_type if conv.channel_id else "",
            }
        )
    return messages


def delete_skill_session(*, session_id: str, external_user_id: str) -> None:
    conv = SkillConversation.objects.filter(session_id=session_id).first()
    if not conv:
        raise SkillChannelChatError("会话不存在", status=404)
    if (conv.external_user_id or "") != (external_user_id or ""):
        raise SkillChannelChatError("无权删除该会话", status=403)
    conv.delete()


def build_skill_chat_params(skill: LLMSkill, user_message: str, request_user, extra: dict | None = None) -> dict:
    tools = resolve_request_tools(None, skill.tools)
    params = {
        "user_message": user_message,
        "skill_id": skill.id,
        "llm_model": skill.llm_model_id,
        "skill_prompt": skill.skill_prompt or "",
        "conversation_window_size": skill.conversation_window_size,
        "show_think": skill.show_think,
        "enable_suggest": skill.enable_suggest,
        "enable_query_rewrite": skill.enable_query_rewrite,
        "skill_type": skill.skill_type,
        "tools": tools,
        "group": (skill.team or [0])[0],
        "wiki_kb_ids": list(skill.wiki_knowledge_bases.values_list("id", flat=True)),
        "skill_params": merge_skill_params([], skill.skill_params or []),
        "temperature": getattr(skill, "temperature", 0.7),
        "username": getattr(request_user, "username", "") or "",
        "user_id": getattr(request_user, "id", None),
        "locale": getattr(request_user, "locale", "en") or "en",
    }
    skill_packages = hydrate_skill_packages(getattr(skill, "skill_packages", []) or [])
    tool_names = []
    for tool in tools or []:
        name = tool.get("name") if isinstance(tool, dict) else None
        if name:
            tool_names.append(name)
    skill_prompt, matched = build_skill_package_prompt(
        base_prompt=params["skill_prompt"],
        skill_packages=skill_packages,
        user_message=user_message,
        available_tool_names=tool_names,
    )
    params["skill_prompt"] = skill_prompt
    params["matched_skill_packages"] = matched
    params["enabled_skill_packages"] = skill_packages
    params.update(build_skill_package_strategy(matched))
    if extra:
        params.update(extra)
    return params


def parse_sse_json_payloads(text: str) -> list[dict]:
    """从 SSE 分片中解析 data: JSON 行。"""
    events = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            events.append(data)
    return events


def assemble_assistant_persist_content(events: list[dict]) -> str:
    """助手落库：有 AG-UI type 时存事件数组，供前端分步回放；否则拼 OpenAI 正文。"""
    typed = [item for item in events if item.get("type")]
    if typed:
        return json.dumps(typed, ensure_ascii=False)
    parts = []
    for data in events:
        delta = (((data.get("choices") or [{}])[0]).get("delta") or {}).get("content")
        if delta:
            parts.append(str(delta))
        elif data.get("content") and "choices" not in data:
            parts.append(str(data["content"]))
    return "".join(parts).strip()


def _looks_like_planned_execution_delta(delta: str) -> bool:
    """TEXT_MESSAGE_CONTENT 误带规划 JSON 时不当成可见正文。"""
    stripped = (delta or "").strip()
    if not stripped.startswith("{"):
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    phase = payload.get("phase")
    return phase in {"planning", "planned", "replanning", "idle", "start", "end"}


def visible_assistant_text(content: str) -> str:
    """给模型的上下文只用可见正文，丢掉计划/工具等 AG-UI 事件。"""
    if not content:
        return ""
    stripped = content.strip()
    if not stripped.startswith("["):
        return content
    try:
        events = json.loads(stripped)
    except json.JSONDecodeError:
        return content
    if not (isinstance(events, list) and events and isinstance(events[0], dict) and events[0].get("type")):
        return content
    parts = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") != "TEXT_MESSAGE_CONTENT":
            continue
        delta = event.get("delta") or ""
        if delta and _looks_like_planned_execution_delta(str(delta)):
            continue
        if delta:
            parts.append(str(delta))
    return "".join(parts).strip()


def _history_from_conversation(conversation: SkillConversation, window: int) -> list[dict]:
    """从落库会话取出上下文，转成 chat_service 使用的 {event, message}。

    当前用户话已作为 user_message 单独传入，最后一条 user 不重复进历史。
    助手 AG-UI 事件数组会先抽成可见正文，避免计划/工具日志进入模型上下文。
    """
    qs = conversation.messages.order_by("-created_at", "-id")[: max(window, 0) * 2]
    items = list(reversed(list(qs)))
    if items and items[-1].role == SkillConversationMessage.ROLE_USER:
        items = items[:-1]
    raw = []
    for msg in items:
        content = msg.content
        if msg.role == SkillConversationMessage.ROLE_ASSISTANT:
            content = visible_assistant_text(content)
        raw.append({"role": msg.role, "content": content})
    return normalize_client_chat_history(raw)


def normalize_client_chat_history(raw) -> list[dict]:
    """把客户端历史统一成 chat_service 使用的 {event, message}。"""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise SkillChannelChatError("chat_history 必须是数组", status=400)
    history = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event") or item.get("role") or "").strip().lower()
        if event in {"assistant", "bot"}:
            event = "bot"
        elif event != "user":
            event = "user"
        message = item.get("message", item.get("content", item.get("text", "")))
        history.append({"event": event, "message": message})
    return history


def split_user_message_and_history(user_message, history: list[dict]) -> tuple:
    """当前用户话从独立字段或历史最后一条 user 取出；其余作为上下文。"""
    if isinstance(user_message, str) and user_message.strip():
        return user_message.strip(), history
    if user_message and not isinstance(user_message, str):
        return user_message, history
    for idx in range(len(history) - 1, -1, -1):
        item = history[idx]
        if item.get("event") != "user":
            continue
        message = item.get("message")
        if isinstance(message, str) and not message.strip():
            continue
        if message in (None, ""):
            continue
        return message, history[:idx]
    raise SkillChannelChatError("user_message 或对话历史中的用户消息必填", status=400)


def truncate_chat_history(history: list[dict], window_size: int) -> list[dict]:
    """只保留最近 window_size 条，超出的不进入后续对话服务。"""
    try:
        window = int(window_size)
    except (TypeError, ValueError):
        window = 10
    if window <= 0:
        return []
    return list(history[-window:])


def execute_skill_channel_im_sync(
    *,
    channel: SkillChannel,
    user_message: str,
    external_user_id: str,
    session_id: str | None = None,
) -> str:
    """IM 异步任务内同步执行单 Agent，落库后返回纯文本回复。"""
    from apps.opspilot.services.chat_service import chat_service

    skill = channel.skill
    conversation = get_or_create_conversation(channel, external_user_id, session_id)
    append_message(conversation, SkillConversationMessage.ROLE_USER, user_message)

    request_user = type("IMUser", (), {"username": external_user_id or "", "id": None, "locale": "en"})()
    params = build_skill_chat_params(skill, user_message, request_user)
    params["chat_history"] = _history_from_conversation(conversation, skill.conversation_window_size or 10)
    result = chat_service.chat(params)
    content = ""
    if isinstance(result, dict):
        content = str(result.get("content") or result.get("message") or "").strip()
    elif result is not None:
        content = str(result).strip()
    if not content:
        content = "处理完成，但未产生可展示内容"
    append_message(conversation, SkillConversationMessage.ROLE_ASSISTANT, content)
    return content


def stream_skill_channel_chat(
    *,
    channel: SkillChannel,
    user_message: str,
    request,
    external_user_id: str,
    session_id: str | None = None,
    identity_user=None,
) -> StreamingHttpResponse:
    skill = channel.skill
    conversation = get_or_create_conversation(channel, external_user_id, session_id)
    append_message(conversation, SkillConversationMessage.ROLE_USER, user_message)

    user = identity_user or request.user
    params = build_skill_chat_params(skill, user_message, user)
    params["chat_history"] = _history_from_conversation(conversation, skill.conversation_window_size or 10)
    params["browser_use_force_task"] = True
    try:
        params[CALLER_IDENTITY_CONFIG_KEY] = capture_caller_identity(request, user)
    except CallerIdentityError as e:
        return create_error_stream_response(str(e))

    current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if current_ip:
        current_ip = current_ip.split(",")[0].strip()
    else:
        current_ip = request.META.get("REMOTE_ADDR", "")

    base_response = stream_agui_chat(params, skill.name, {}, current_ip, user_message, skill_id=skill.id)
    return _wrap_stream_persist_assistant(base_response, conversation.id)


async def _aiter_stream(iterable):
    """兼容 StreamingHttpResponse 的同步/异步迭代内容。"""
    if hasattr(iterable, "__aiter__"):
        async for item in iterable:
            yield item
        return
    for item in iterable:
        yield item


def _wrap_stream_persist_assistant(response: StreamingHttpResponse, conversation_id: int) -> StreamingHttpResponse:
    """包装 SSE：落库 AG-UI 事件数组（或 OpenAI 正文）。失败不影响流式输出。"""

    original = response.streaming_content

    async def generator():
        events: list[dict] = []
        try:
            async for piece in _aiter_stream(original):
                text = piece.decode("utf-8") if isinstance(piece, (bytes, bytearray)) else str(piece)
                yield piece
                events.extend(parse_sse_json_payloads(text))
        finally:
            content = assemble_assistant_persist_content(events)
            if content:
                try:
                    await sync_to_async(append_message)(
                        await sync_to_async(SkillConversation.objects.get)(id=conversation_id),
                        SkillConversationMessage.ROLE_ASSISTANT,
                        content,
                    )
                except Exception:
                    logger.exception("persist skill channel assistant message failed: conversation_id=%s", conversation_id)

    wrapped = StreamingHttpResponse(generator(), content_type=response["Content-Type"])
    for key, value in response.items():
        wrapped[key] = value
    return wrapped


PLATFORM_OR_WEB = {SkillChannelChoices.PLATFORM, SkillChannelChoices.WEB_CHAT}
EMBEDDED = {SkillChannelChoices.EMBEDDED_CHAT}
