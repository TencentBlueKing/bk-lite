"""Estimate the next LLM packet for a persisted skill session (usage ring)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.context_usage import summarize_llm_context_usage
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.message_trim import trim_messages
from apps.opspilot.models import SkillConversation, SkillConversationMessage
from apps.opspilot.services.history_service import HistoryService
from apps.opspilot.services.llm_context_budget import DEFAULT_CHAT_SCENE_OUTPUT_TOKENS, working_budget_for_model
from apps.opspilot.services.skill_channel_chat_service import build_skill_chat_params, normalize_client_chat_history, visible_assistant_text

_SESSION_USAGE_SKIPPED = "event=llm_context_usage_session_skipped failed_stage=session_messages error_type=%s"


def _history_for_session(conversation: SkillConversation) -> list[dict[str, Any]]:
    skill = conversation.skill
    window = getattr(skill, "conversation_window_size", None) or 10
    try:
        window = max(int(window), 0)
    except (TypeError, ValueError):
        window = 10
    if window <= 0:
        return []
    items = list(reversed(list(conversation.messages.order_by("-created_at", "-id")[:window])))
    raw = []
    for msg in items:
        content = msg.content
        if msg.role == SkillConversationMessage.ROLE_ASSISTANT:
            content = visible_assistant_text(content)
        raw.append({"role": msg.role, "content": content})
    return HistoryService.process_chat_history(normalize_client_chat_history(raw), window, [])


def _history_to_messages(history: list[dict[str, Any]], system_prompt: str) -> list:
    messages = []
    if (system_prompt or "").strip():
        messages.append(SystemMessage(content=system_prompt))
    for item in history:
        event = str(item.get("event") or "").strip().lower()
        text = item.get("message")
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        if event == "user":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))
    return messages


def _last_user_text(history: list[dict[str, Any]]) -> str:
    for item in reversed(history):
        if item.get("event") != "user":
            continue
        message = item.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return ""


def summarize_skill_session_usage(conversation: SkillConversation) -> dict[str, Any] | None:
    """Count the next packet from stored history. None if history is off or empty."""
    skill = getattr(conversation, "skill", None)
    if skill is None or not getattr(skill, "enable_conversation_history", False):
        return None
    try:
        history = _history_for_session(conversation)
        if not history:
            return None
        params = build_skill_chat_params(
            skill,
            _last_user_text(history),
            SimpleNamespace(username="", id=None, locale="en"),
        )
        messages = _history_to_messages(history, params.get("skill_prompt") or "")
        llm_model = getattr(skill, "llm_model", None)
        derived = working_budget_for_model(llm_model, scene_output_default=DEFAULT_CHAT_SCENE_OUTPUT_TOKENS)
        model_name = str(getattr(llm_model, "model_name", None) or "gpt-4o")
        messages = trim_messages(
            messages,
            MessageTrimConfig(enabled=True, max_single_message_tokens=derived.single_message_tokens),
            model_name,
        )
        request = BasicLLMRequest(
            model=model_name,
            extra_config={
                "input_working_tokens": derived.input_working_tokens,
                "context_window_tokens": derived.window_tokens,
            },
            compaction_max_token_threshold=derived.compaction_threshold_tokens,
        )
        return summarize_llm_context_usage(
            messages,
            request=request,
            tools=params.get("tools"),
            model_name=model_name,
        )
    except Exception as exc:
        logger.debug(_SESSION_USAGE_SKIPPED, type(exc).__name__)
        return None
