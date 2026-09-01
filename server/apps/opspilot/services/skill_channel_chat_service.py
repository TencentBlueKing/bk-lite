"""智能体渠道对话：鉴权、会话持久化、SSE 执行。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

from apps.base.models import UserAPISecret
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SKILL_CHANNEL_SKIP_ORG_CHECK, SkillChannelChoices
from apps.opspilot.metis.llm.chain.token_utils import count_text_tokens
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.caller_identity import CALLER_IDENTITY_CONFIG_KEY, CallerIdentityError, capture_caller_identity
from apps.opspilot.services.history_service import HistoryService
from apps.opspilot.services.skill_channel_service import channel_allows_team, resolve_ops_pilot_guest_id
from apps.opspilot.services.skill_package.runtime import build_skill_package_prompt, build_skill_package_strategy, hydrate_skill_packages
from apps.opspilot.utils.agui_chat import stream_agui_chat
from apps.opspilot.utils.prompt_utils import merge_skill_params
from apps.opspilot.utils.skill_execution_params import resolve_request_tools
from apps.opspilot.utils.sse_chat import create_error_stream_response

PAGE_CONTEXT_TEXT_BUDGET = 8000
PAGE_CONTEXT_MAX_IMAGES = 6
PAGE_CONTEXT_MAX_IMAGE_CHARS = 500 * 1024
PAGE_CONTEXT_GUIDE = (
    "以下是用户当前正在查看的页面快照，仅当问题与页面相关时参考。" "只回答用户这一轮提出的问题，不要复述历史里已分析过、且本轮未点名的图表。" "时间范围、横轴起止与 KPI 一律以 <current_page> 本轮快照为准，" "禁止沿用对话历史里过期的时间窗描述。"
)
PAGE_CONTEXT_FOCUSED_GUIDE = (
    "本轮用户问题是「{question}」，已定位到图表{names}。"
    "只根据本轮 <current_page> 中的截图与文字回答这一问，"
    "不要沿用上一问的结论、表格、图表名或时间范围。"
    "截图上可能没有标题，以这段文字中的图表名、KPI 快照与「时间筛选/横轴」说明为准。"
    "问使用率或容量时优先用 KPI 快照里的「指标名: 数值」，不要把吞吐、流量或错误速率图当成占用百分比。"
    "禁止回答、复述或续写历史对话里已经分析过的其它图表。"
)
# ~600px 截图按 OpenAI high-detail 估算：ceil(600/512)^2 * 170 + 85
PAGE_CONTEXT_IMAGE_TOKEN_ESTIMATE = 765
# 单轮页面内容（快照+图）估算超限：拒绝问答；会话累计超限：提示新开会话。测试可 patch。
PAGE_CONTEXT_SINGLE_TURN_MAX_TOKENS = 20000
PAGE_CONTEXT_SESSION_MAX_TOKENS = 80000
PAGE_CONTEXT_TOO_LARGE_MESSAGE = "当前页面内容过多，无法进行问答"
PAGE_CONTEXT_SESSION_OVERFLOW_MESSAGE = "上下文过长，请新开会话"


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


def persistable_user_message_text(user_message) -> str:
    """落库只用用户原文；多模态 list 抽出纯文本，避免把快照/图片写入 TextField。"""
    if isinstance(user_message, str):
        return user_message
    if isinstance(user_message, list):
        text, _images = HistoryService.process_user_message_and_images(user_message)
        return text if isinstance(text, str) else ""
    return str(user_message or "")


def _split_user_content(user_message) -> tuple[str, list[dict]]:
    if isinstance(user_message, list):
        text, image_urls = HistoryService.process_user_message_and_images(user_message)
        images = [{"type": "image_url", "image_url": url} for url in image_urls if url]
        return (text if isinstance(text, str) else ""), images
    return str(user_message or ""), []


def _section_priority(section) -> int:
    if not isinstance(section, dict):
        return 0
    try:
        return int(section.get("priority") or 0)
    except (TypeError, ValueError):
        return 0


def _caption_title(caption: str) -> str:
    return str(caption or "").split("；", 1)[0].strip()


def _normalize_chart_text(value: str) -> str:
    return "".join(str(value or "").split()).lower()


def _is_generic_chart_title(title: str) -> bool:
    text = str(title or "").strip()
    return (not text) or text == "图表" or bool(re.fullmatch(r"(value|series)\d*", text, re.I))


# 标题与问法常共用的主题词；图名级匹配不看图例，避免「CPU 使用时间」命中「资源使用趋势」里的 CPU 使用率。
_CHART_TOPIC_MARKERS = (
    "时间分布",
    "使用时间",
    "iowait",
    "cpu",
    "负载",
    "磁盘",
    "内存",
    "网络",
    "吞吐",
    "错误",
)
# 问法带了更细的度量词时，禁止只靠「磁盘/网络」这种粗主题命中另一类图（使用率 ≠ 吞吐）。
_CHART_QUALIFIERS = (
    "使用率",
    "吞吐",
    "错误",
    "时间分布",
    "使用时间",
    "负载",
)
_QUESTION_TITLE_ALIASES = (
    ("使用时间", "时间分布"),
    ("时间分布", "使用时间"),
)


def _chart_qualifiers(text: str) -> set[str]:
    found = {item for item in _CHART_QUALIFIERS if item in text}
    if "使用时间" in found:
        found.add("时间分布")
    if "时间分布" in found:
        found.add("使用时间")
    return found


def _qualifiers_conflict(left: str, right: str) -> bool:
    left_quals = _chart_qualifiers(left)
    right_quals = _chart_qualifiers(right)
    return bool(left_quals and right_quals and left_quals.isdisjoint(right_quals))


def chart_title_matches_question(title: str, question: str) -> bool:
    t = _normalize_chart_text(title)
    q = _normalize_chart_text(question)
    if not t or _is_generic_chart_title(title) or len(q) < 2:
        return False
    if len(t) >= 2 and t in q:
        return True
    core = t[:-3] if t.endswith("top") else t
    if core.endswith("趋势"):
        core = core[:-2]
    if len(core) >= 2 and core in q:
        return True
    if 2 <= len(q) <= 12 and q in t:
        return True
    if any(alias in q and target in t for alias, target in _QUESTION_TITLE_ALIASES):
        return True
    if _qualifiers_conflict(t, q):
        return False
    question_quals = _chart_qualifiers(q)
    if question_quals and not (question_quals & _chart_qualifiers(t)):
        return False
    return any(marker in t and marker in q for marker in _CHART_TOPIC_MARKERS)


def _caption_series_matches_question(caption: str, question: str) -> bool:
    """序列里出现「磁盘使用率」这类完整度量时，允许命中综合趋势图。"""
    cap = _normalize_chart_text(caption)
    q = _normalize_chart_text(question)
    if not cap or len(q) < 2:
        return False
    question_quals = _chart_qualifiers(q)
    if not question_quals or not (question_quals & _chart_qualifiers(cap)):
        return False
    if _qualifiers_conflict(cap, q):
        return False
    return any(marker in cap and marker in q for marker in _CHART_TOPIC_MARKERS)


def chart_matches_question(caption: str, question: str) -> bool:
    title = _caption_title(caption)
    if chart_title_matches_question(title, question):
        return True
    return _caption_series_matches_question(caption, question)


def _visible_chart_captions(snapshot: dict) -> list[str]:
    captions: list[str] = []
    for image in snapshot.get("images") or []:
        caption = str(image.get("caption") or "").strip()
        if caption and not _is_generic_chart_title(_caption_title(caption)):
            captions.append(caption)
    for section in snapshot.get("sections") or []:
        if section.get("id") != "visible-charts":
            continue
        for line in str(section.get("content") or "").splitlines():
            text = line.split(".", 1)[-1].strip() if "." in line[:4] else line.strip()
            if text and not _is_generic_chart_title(_caption_title(text)):
                captions.append(text)
    return captions


def _visible_chart_titles(snapshot: dict) -> list[str]:
    return [_caption_title(caption) for caption in _visible_chart_captions(snapshot)]


def _unique_titles(titles: list[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for title in titles:
        key = _normalize_chart_text(title)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(title)
    return kept


def _page_context_guide(focused_titles: list[str], question: str = "") -> str:
    titles = _unique_titles(focused_titles)
    if not titles:
        return PAGE_CONTEXT_GUIDE
    names = "、".join(f"《{title}》" for title in titles)
    return PAGE_CONTEXT_FOCUSED_GUIDE.format(question=str(question or "").strip(), names=names)


def _focused_titles_from_page_context(question: str, page_context) -> list[str]:
    snapshot = _sanitize_page_context(page_context)
    if not snapshot:
        return []
    snapshot = _focus_page_context(question, snapshot)
    return [str(title) for title in (snapshot.get("_focused_titles") or []) if title]


def _history_for_focused_charts(history: list[dict], focused_titles: list[str]) -> list[dict]:
    """本轮已点名图表时丢掉历史。

     每轮都会重新采集页面截图；保留历史会让模型复述上一问结论
    （含用户切换时间筛选后仍沿用旧时间窗）。未点名图表的追问仍保留历史。
    """
    if not focused_titles or not history:
        return history
    return []


def _focus_page_context(question: str, snapshot: dict) -> dict:
    """问题点名了图表时，只保留对应截图，避免把上一问的图再喂一遍。"""
    images = [item for item in (snapshot.get("images") or []) if isinstance(item, dict)]
    if not images or not str(question or "").strip():
        return snapshot
    matched = _unique_titles([_caption_title(caption) for caption in _visible_chart_captions(snapshot) if chart_matches_question(caption, question)])
    if not matched:
        return snapshot
    kept = []
    for image in images:
        caption = str(image.get("caption") or "")
        title = _caption_title(caption)
        if title in matched or chart_matches_question(caption, question):
            kept.append(image)
    next_snapshot = {**snapshot, "images": kept, "_focused_titles": matched, "_focus_question": str(question or "").strip()}
    sections = []
    for section in snapshot.get("sections") or []:
        if section.get("id") != "visible-charts":
            sections.append(section)
            continue
        lines = [f"{idx}. {image.get('caption')}" for idx, image in enumerate(kept, start=1) if image.get("caption")]
        if not lines:
            continue
        sections.append({**section, "content": "\n".join(lines)})
    next_snapshot["sections"] = sections
    return next_snapshot


def _sanitize_page_context(page_context) -> dict | None:
    if not isinstance(page_context, dict) or not page_context:
        return None
    sections = [item for item in (page_context.get("sections") or []) if isinstance(item, dict)]
    sections.sort(key=_section_priority, reverse=True)
    kept_sections = []
    used = 0
    for section in sections:
        content = str(section.get("content") or "")
        if not content.strip():
            continue
        remaining = PAGE_CONTEXT_TEXT_BUDGET - used
        if remaining <= 0:
            break
        if len(content) > remaining:
            if used == 0:
                content = content[:remaining]
            else:
                continue
        kept_sections.append(
            {
                "id": section.get("id") or "",
                "label": section.get("label") or "",
                "content": content,
                "priority": _section_priority(section),
            }
        )
        used += len(content)

    images = []
    for item in page_context.get("images") or []:
        if len(images) >= PAGE_CONTEXT_MAX_IMAGES:
            break
        if not isinstance(item, dict):
            continue
        data_url = str(item.get("dataUrl") or item.get("data_url") or "")
        # 只收内联 data:image，拒绝 http(s) 等远程地址，避免经模型侧回源造成 SSRF。
        if not data_url.lower().startswith("data:image/"):
            continue
        if len(data_url) > PAGE_CONTEXT_MAX_IMAGE_CHARS:
            continue
        images.append({"caption": str(item.get("caption") or ""), "dataUrl": data_url})

    if not kept_sections and not images and not (page_context.get("title") or page_context.get("url")):
        return None
    return {
        "url": str(page_context.get("url") or ""),
        "app": str(page_context.get("app") or ""),
        "title": str(page_context.get("title") or ""),
        "sections": kept_sections,
        "images": images,
    }


def _render_page_context_block(snapshot: dict, question: str = "") -> str:
    focused = [str(title) for title in (snapshot.get("_focused_titles") or []) if title]
    q = str(question or snapshot.get("_focus_question") or "")
    lines = [_page_context_guide(focused, q), "<current_page>"]
    if snapshot.get("url"):
        lines.append(f"url: {snapshot['url']}")
    if snapshot.get("app"):
        lines.append(f"app: {snapshot['app']}")
    if snapshot.get("title"):
        lines.append(f"title: {snapshot['title']}")
    for section in snapshot.get("sections") or []:
        label = section.get("label") or section.get("id") or "section"
        lines.append(f"## {label}")
        lines.append(section.get("content") or "")
    lines.append("</current_page>")
    return "\n".join(lines).strip()


def _count_prompt_tokens(text: str) -> int:
    return count_text_tokens(str(text or ""))


def _injected_user_text(user_message) -> str:
    if isinstance(user_message, list):
        text, _images = HistoryService.process_user_message_and_images(user_message)
        return text if isinstance(text, str) else ""
    return str(user_message or "")


def _history_token_count(history) -> tuple[int, int]:
    parts = []
    for item in history or []:
        if isinstance(item, dict):
            parts.append(str(item.get("message") or ""))
    return len(history or []), _count_prompt_tokens("\n".join(parts))


def build_page_context_ingest_report(
    *,
    persist_text: str,
    injected_user_message,
    page_context,
    skill_prompt: str = "",
    chat_history=None,
) -> dict | None:
    """统计当轮入库 prompt：用户原文、页面快照、系统提示、历史；图片只记估算、不落 base64。"""
    snapshot = _sanitize_page_context(page_context)
    if snapshot:
        snapshot = _focus_page_context(persist_text, snapshot)
    if not snapshot:
        return None
    captions = [item.get("caption") for item in snapshot.get("images") or [] if item.get("caption")]
    snapshot_text = _render_page_context_block(snapshot, persist_text)
    if captions:
        snapshot_text = snapshot_text + "\n图表说明:\n" + "\n".join(f"- {caption}" for caption in captions)
    injected_text = _injected_user_text(injected_user_message)
    sections = []
    for section in snapshot.get("sections") or []:
        content = str(section.get("content") or "")
        sections.append(
            {
                "id": section.get("id") or "",
                "label": section.get("label") or "",
                "chars": len(content),
                "tokens": _count_prompt_tokens(content),
            }
        )
    images = []
    for idx, item in enumerate(snapshot.get("images") or []):
        data_url = str(item.get("dataUrl") or "")
        images.append(
            {
                "idx": idx,
                "caption": str(item.get("caption") or ""),
                "chars": len(data_url),
                "est_tokens": PAGE_CONTEXT_IMAGE_TOKEN_ESTIMATE,
            }
        )
    history_count, history_tokens = _history_token_count(chat_history)
    question_tokens = _count_prompt_tokens(persist_text)
    snapshot_tokens = _count_prompt_tokens(snapshot_text)
    skill_prompt_tokens = _count_prompt_tokens(skill_prompt)
    injected_tokens = _count_prompt_tokens(injected_text)
    image_est_tokens = PAGE_CONTEXT_IMAGE_TOKEN_ESTIMATE * len(images)
    return {
        "url": snapshot.get("url") or "",
        "app": snapshot.get("app") or "",
        "title": snapshot.get("title") or "",
        "user_question": persist_text,
        "user_question_tokens": question_tokens,
        "snapshot_text": snapshot_text,
        "snapshot_tokens": snapshot_tokens,
        "injected_user_text": injected_text,
        "injected_user_tokens": injected_tokens,
        "sections": sections,
        "images": images,
        "image_count": len(images),
        "image_est_tokens": image_est_tokens,
        "skill_prompt_tokens": skill_prompt_tokens,
        "history_messages": history_count,
        "history_tokens": history_tokens,
        "estimated_input_tokens": question_tokens + snapshot_tokens + skill_prompt_tokens + history_tokens + image_est_tokens,
    }


def log_page_context_ingest(report: dict) -> None:
    """页面身份与问答摘要写 INFO；分节、图片与 token 明细写 DEBUG。"""
    logger.info(
        "page_context ingest: title=%s app=%s url=%s images=%s estimated_tokens=%s question=%s",
        report.get("title") or "-",
        report.get("app") or "-",
        report.get("url") or "-",
        report.get("image_count") or 0,
        report.get("estimated_input_tokens") or 0,
        report.get("user_question") or "",
    )
    logger.debug(
        "page_context user_question tokens=%s text=%s",
        report.get("user_question_tokens") or 0,
        report.get("user_question") or "",
    )
    for section in report.get("sections") or []:
        logger.debug(
            "page_context section id=%s label=%s chars=%s tokens=%s",
            section.get("id") or "-",
            section.get("label") or "-",
            section.get("chars") or 0,
            section.get("tokens") or 0,
        )
    for image in report.get("images") or []:
        logger.debug(
            "page_context image idx=%s caption=%s chars=%s est_tokens=%s",
            image.get("idx"),
            image.get("caption") or "-",
            image.get("chars") or 0,
            image.get("est_tokens") or 0,
        )
    logger.debug(
        "page_context ingest_total user_question_tokens=%s snapshot_tokens=%s "
        "image_est_tokens=%s skill_prompt_tokens=%s history_messages=%s history_tokens=%s "
        "estimated_input_tokens=%s (image_est uses %s/image; billed usage is AGUI token usage after stream)",
        report.get("user_question_tokens") or 0,
        report.get("snapshot_tokens") or 0,
        report.get("image_est_tokens") or 0,
        report.get("skill_prompt_tokens") or 0,
        report.get("history_messages") or 0,
        report.get("history_tokens") or 0,
        report.get("estimated_input_tokens") or 0,
        PAGE_CONTEXT_IMAGE_TOKEN_ESTIMATE,
    )


def drop_images_from_user_message(user_message):
    """非多模态模型：去掉全部 image_url，保留文本与图表说明。"""
    if not isinstance(user_message, list):
        return user_message
    kept = []
    dropped = 0
    for item in user_message:
        if isinstance(item, dict) and item.get("type") == "image_url":
            dropped += 1
            continue
        kept.append(item)
    if dropped:
        logger.info("page_context images dropped: count=%s reason=model_not_multimodal", dropped)
    if len(kept) == 1 and isinstance(kept[0], dict) and kept[0].get("type") == "message":
        return kept[0].get("message") or ""
    return kept


def page_context_budget_error(ingest_report: dict | None) -> str | None:
    """单轮页面内容超限 / 会话累计超限时返回错误文案。"""
    if not ingest_report:
        return None
    snapshot_tokens = int(ingest_report.get("snapshot_tokens") or 0)
    image_est = int(ingest_report.get("image_est_tokens") or 0)
    if snapshot_tokens + image_est > PAGE_CONTEXT_SINGLE_TURN_MAX_TOKENS:
        return PAGE_CONTEXT_TOO_LARGE_MESSAGE
    estimated = int(ingest_report.get("estimated_input_tokens") or 0)
    if estimated > PAGE_CONTEXT_SESSION_MAX_TOKENS:
        return PAGE_CONTEXT_SESSION_OVERFLOW_MESSAGE
    return None


def inject_page_context(user_message, page_context, mode: str = "inline"):
    """把当轮 page_context 拼进当前用户消息；不写入会话历史。mode 仅实现 inline。"""
    if not page_context:
        return user_message
    if mode != "inline":
        logger.warning("page_context inject mode=%s not implemented, skip", mode)
        return user_message
    try:
        snapshot = _sanitize_page_context(page_context)
        if not snapshot:
            return user_message
        text, existing_images = _split_user_content(user_message)
        snapshot = _focus_page_context(text, snapshot)
        page_images = [{"type": "image_url", "image_url": item["dataUrl"]} for item in snapshot.get("images") or []]
        captions = [item.get("caption") for item in snapshot.get("images") or [] if item.get("caption")]
        block = _render_page_context_block(snapshot, text)
        if captions:
            block = block + "\n图表说明:\n" + "\n".join(f"- {caption}" for caption in captions)
        focused = [str(title) for title in (snapshot.get("_focused_titles") or []) if title]
        constraint = _page_context_guide(focused, text) if focused else ""
        head = "\n\n".join(part for part in (constraint, text) if part)
        merged_text = f"{head}\n\n{block}".strip() if head else block
        if not page_images and not existing_images:
            return merged_text
        return [*existing_images, *page_images, {"type": "message", "message": merged_text}]
    except Exception:
        logger.exception("inject_page_context failed, continue without page context")
        return user_message


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


def _owned_skill_conversation(*, session_id: str, external_user_id: str) -> SkillConversation:
    conv = SkillConversation.objects.filter(session_id=session_id, is_active=True).select_related("channel", "skill", "skill__llm_model").first()
    if not conv:
        raise SkillChannelChatError("会话不存在", status=404)
    if (conv.external_user_id or "") != (external_user_id or ""):
        raise SkillChannelChatError("无权查看该会话", status=403)
    return conv


def _serialize_session_messages(conv: SkillConversation) -> list[dict]:
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


def get_skill_session_messages(*, session_id: str, external_user_id: str) -> list[dict]:
    return _serialize_session_messages(_owned_skill_conversation(session_id=session_id, external_user_id=external_user_id))


def get_skill_session_history(*, session_id: str, external_user_id: str) -> tuple[list[dict], SkillConversation]:
    conv = _owned_skill_conversation(session_id=session_id, external_user_id=external_user_id)
    return _serialize_session_messages(conv), conv


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
    typed = [item for item in events if item.get("type") and not (item.get("type") == "CUSTOM" and item.get("name") == "stream_keepalive")]
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
    page_context=None,
) -> StreamingHttpResponse:
    skill = channel.skill
    conversation = get_or_create_conversation(channel, external_user_id, session_id)
    persist_text = persistable_user_message_text(user_message)
    append_message(conversation, SkillConversationMessage.ROLE_USER, persist_text)

    user = identity_user or request.user
    params = build_skill_chat_params(skill, persist_text, user)
    params["chat_history"] = _history_from_conversation(conversation, skill.conversation_window_size or 10)
    focused_titles = _focused_titles_from_page_context(persist_text, page_context)
    params["chat_history"] = _history_for_focused_charts(params["chat_history"], focused_titles)
    params["user_message"] = inject_page_context(user_message, page_context, mode="inline")
    llm_model = getattr(skill, "llm_model", None)
    report_context = page_context
    if llm_model is not None and not getattr(llm_model, "is_multimodal", True):
        params["user_message"] = drop_images_from_user_message(params["user_message"])
        if isinstance(page_context, dict):
            report_context = {**page_context, "images": []}
    params["browser_use_force_task"] = True
    ingest_kwargs: dict[str, Any] = {}
    ingest_report = build_page_context_ingest_report(
        persist_text=persist_text,
        injected_user_message=params["user_message"],
        page_context=report_context,
        skill_prompt=params.get("skill_prompt") or "",
        chat_history=params.get("chat_history") or [],
    )
    if ingest_report:
        log_page_context_ingest(ingest_report)
        ingest_kwargs["page_context_ingest"] = ingest_report
        budget_error = page_context_budget_error(ingest_report)
        if budget_error:
            logger.info(
                "page_context rejected: error=%s title=%s estimated_tokens=%s snapshot_tokens=%s history_messages=%s",
                budget_error,
                ingest_report.get("title") or "-",
                ingest_report.get("estimated_input_tokens") or 0,
                ingest_report.get("snapshot_tokens") or 0,
                ingest_report.get("history_messages") or 0,
            )
            return create_error_stream_response(budget_error)
    else:
        # 无 page_context 是 skill channel 聊天的常见路径，只作 DEBUG 诊断，不记问句。
        logger.debug("page_context absent: session_id=%s", session_id or "-")
    try:
        params[CALLER_IDENTITY_CONFIG_KEY] = capture_caller_identity(request, user)
    except CallerIdentityError as e:
        return create_error_stream_response(str(e))

    current_ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if current_ip:
        current_ip = current_ip.split(",")[0].strip()
    else:
        current_ip = request.META.get("REMOTE_ADDR", "")

    base_response = stream_agui_chat(params, skill.name, ingest_kwargs, current_ip, persist_text, skill_id=skill.id)
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
