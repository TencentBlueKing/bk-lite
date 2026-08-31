"""Trim then compact conversation messages before an LLM call."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.compaction import CompactionConfig, compact_messages
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.message_trim import trim_messages
from apps.opspilot.metis.llm.chain.token_utils import count_message_tokens, count_text_tokens

LLM_CONTEXT_WINDOW_EXCEEDED = "llm_context_window_exceeded"


class LLMContextWindowExceeded(Exception):
    """Irreducible core (system + current user + tools) exceeds input working budget."""

    def __init__(self, message: str, *, code: str = LLM_CONTEXT_WINDOW_EXCEEDED):
        self.code = code
        super().__init__(message)


def _as_trim_config(raw) -> MessageTrimConfig:
    if isinstance(raw, MessageTrimConfig):
        return raw
    return MessageTrimConfig.model_validate(raw or {})


def _compaction_config(request: BasicLLMRequest) -> CompactionConfig:
    return CompactionConfig(
        enabled=bool(getattr(request, "compaction_enabled", True)),
        max_token_threshold=int(getattr(request, "compaction_max_token_threshold", 0) or 0),
        keep_recent_messages=int(getattr(request, "compaction_keep_recent_messages", 12) or 12),
        summary_max_tokens=int(getattr(request, "compaction_summary_max_tokens", 2000) or 2000),
    )


def _input_working_tokens(request: BasicLLMRequest) -> int:
    extra = getattr(request, "extra_config", None) or {}
    raw = extra.get("input_working_tokens")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _last_human_index(messages: List[BaseMessage]) -> int:
    last_idx = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_idx = index
    return last_idx


def _trim_preserving_current_user(messages: List[BaseMessage], config: MessageTrimConfig, model_name: str) -> List[BaseMessage]:
    last_idx = _last_human_index(messages)
    if last_idx < 0:
        return trim_messages(messages, config, model_name)
    prefix = trim_messages(messages[:last_idx], config, model_name)
    current = messages[last_idx]
    suffix = trim_messages(messages[last_idx + 1 :], config, model_name)
    return prefix + [current] + suffix


def _tool_definition_tokens(tools: Optional[Iterable[Any]], model_name: str) -> int:
    if not tools:
        return 0
    parts = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "")
        description = str(getattr(tool, "description", "") or "")
        parts.append(f"{name}\n{description}")
    return count_text_tokens("\n".join(parts), model_name)


def _irreducible_core(messages: List[BaseMessage]) -> List[BaseMessage]:
    system_messages = [message for message in messages if isinstance(message, SystemMessage)]
    last_idx = _last_human_index(messages)
    if last_idx < 0:
        return system_messages
    current = messages[last_idx]
    if current in system_messages:
        return system_messages
    return system_messages + [current]


async def prepare_messages_for_llm(
    messages: List[BaseMessage],
    *,
    request: BasicLLMRequest,
    isolated_llm,
    tools: Optional[Iterable[Any]] = None,
) -> List[BaseMessage]:
    """Apply single-message trim, then compaction; fail if the core still cannot fit."""

    model_name = str(getattr(request, "model", "") or "gpt-4o")
    trim_config = _as_trim_config(getattr(request, "message_trim_config", None))
    prepared = _trim_preserving_current_user(list(messages or []), trim_config, model_name)
    compaction = _compaction_config(request)
    if compaction.enabled and compaction.max_token_threshold > 0 and isolated_llm is not None:
        prepared = await compact_messages(prepared, isolated_llm, config=compaction, model_name=model_name)

    input_working = _input_working_tokens(request)
    if input_working <= 0:
        return prepared

    core = _irreducible_core(prepared)
    core_tokens = count_message_tokens(core, model_name) + _tool_definition_tokens(tools, model_name)
    if core_tokens <= input_working:
        return prepared

    last_idx = _last_human_index(prepared)
    current_text = ""
    if last_idx >= 0:
        content = getattr(prepared[last_idx], "content", "")
        current_text = content if isinstance(content, str) else str(content)
    logger.warning(
        "event=llm_context_window_exceeded failed_stage=prepare_messages error_type=%s core_tokens=%s input_working_tokens=%s",
        LLM_CONTEXT_WINDOW_EXCEEDED,
        core_tokens,
        input_working,
    )
    raise LLMContextWindowExceeded(
        f"{LLM_CONTEXT_WINDOW_EXCEEDED}: irreducible core exceeds input working budget "
        f"(core_tokens={core_tokens}, input_working_tokens={input_working}, current_user_len={len(current_text)})"
    )
