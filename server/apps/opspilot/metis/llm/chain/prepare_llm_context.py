"""Trim then compact conversation messages before an LLM call."""

from __future__ import annotations

from typing import Any, Iterable

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.compaction import CompactionConfig, compact_leaving_current_user, compact_messages
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, MessageTrimConfig
from apps.opspilot.metis.llm.chain.message_trim import trim_messages
from apps.opspilot.metis.llm.chain.token_utils import count_llm_request_tokens, count_tool_schema_tokens

LLM_CONTEXT_WINDOW_EXCEEDED = "llm_context_window_exceeded"
CLEARED_TOOL_RESULT_PLACEHOLDER = "[工具结果已清除，需要时请重新调用]"
KEEP_RECENT_TOOL_RESULTS = 4
CONTEXT_REFIT_LOG = "event=llm_context_refit keep_recent=%s packet_tokens=%s input_working_tokens=%s"
CONTEXT_COLLAPSED_TO_CORE_LOG = "event=llm_context_collapsed_to_core packet_tokens=%s core_tokens=%s input_working_tokens=%s"


class LLMContextWindowExceeded(Exception):
    """Irreducible core (system + current user + tools) exceeds input working budget."""

    def __init__(self, message: str, *, code: str = LLM_CONTEXT_WINDOW_EXCEEDED):
        self.code = code
        super().__init__(message)


def _as_trim_config(raw) -> MessageTrimConfig:
    if isinstance(raw, MessageTrimConfig):
        return raw
    return MessageTrimConfig.model_validate(raw or {})


def _compaction_config(request: BasicLLMRequest, *, keep_recent_messages: int | None = None) -> CompactionConfig:
    keep = keep_recent_messages
    if keep is None:
        keep = int(getattr(request, "compaction_keep_recent_messages", 12) or 12)
    return CompactionConfig(
        enabled=bool(getattr(request, "compaction_enabled", True)),
        max_token_threshold=int(getattr(request, "compaction_max_token_threshold", 0) or 0),
        keep_recent_messages=int(keep),
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


def _last_human_index(messages: list[BaseMessage]) -> int:
    last_idx = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_idx = index
    return last_idx


def _trim_preserving_current_user(messages: list[BaseMessage], config: MessageTrimConfig, model_name: str) -> list[BaseMessage]:
    last_idx = _last_human_index(messages)
    if last_idx < 0:
        return trim_messages(messages, config, model_name)
    prefix = trim_messages(messages[:last_idx], config, model_name)
    current = messages[last_idx]
    suffix = trim_messages(messages[last_idx + 1 :], config, model_name)
    return prefix + [current] + suffix


def _irreducible_core(messages: list[BaseMessage]) -> list[BaseMessage]:
    system_messages = [message for message in messages if isinstance(message, SystemMessage)]
    last_idx = _last_human_index(messages)
    if last_idx < 0:
        return system_messages
    current = messages[last_idx]
    if current in system_messages:
        return system_messages
    return system_messages + [current]


def drop_old_tool_results(
    messages: list[BaseMessage],
    *,
    keep_recent: int = KEEP_RECENT_TOOL_RESULTS,
) -> list[BaseMessage]:
    """Clear older tool bodies; keep tool_call pairing so the model can re-call if needed."""
    tool_indexes = [
        index
        for index, message in enumerate(messages or [])
        if isinstance(message, ToolMessage) and getattr(message, "content", None) != CLEARED_TOOL_RESULT_PLACEHOLDER
    ]
    keep = max(int(keep_recent), 0)
    if keep >= len(tool_indexes):
        return list(messages or [])
    drop = set(tool_indexes if keep == 0 else tool_indexes[:-keep])
    prepared: list[BaseMessage] = []
    for index, message in enumerate(messages or []):
        if index not in drop:
            prepared.append(message)
            continue
        prepared.append(
            ToolMessage(
                content=CLEARED_TOOL_RESULT_PLACEHOLDER,
                tool_call_id=getattr(message, "tool_call_id", "") or "",
                name=getattr(message, "name", None),
                status=getattr(message, "status", None),
            )
        )
    return prepared


def _smaller_keep_recent(keep: int) -> int | None:
    if keep > 6:
        return 6
    if keep > 2:
        return 2
    return None


def _drop_tools_toward_budget(
    prepared: list[BaseMessage],
    *,
    input_working: int,
    tools: Iterable[Any] | None,
    model_name: str,
    force_compact: bool,
) -> list[BaseMessage]:
    packet_tokens = count_llm_request_tokens(prepared, tools, model_name)
    if packet_tokens > input_working or force_compact:
        keep_recent = 0 if force_compact else KEEP_RECENT_TOOL_RESULTS
        prepared = drop_old_tool_results(prepared, keep_recent=keep_recent)
        packet_tokens = count_llm_request_tokens(prepared, tools, model_name)
        if packet_tokens > input_working and keep_recent > 0:
            prepared = drop_old_tool_results(prepared, keep_recent=0)
    return prepared


async def _refit_packet_to_working_budget(
    prepared: list[BaseMessage],
    *,
    request: BasicLLMRequest,
    isolated_llm,
    tools: Iterable[Any] | None,
    model_name: str,
    trim_config: MessageTrimConfig,
    compaction: CompactionConfig,
    input_working: int,
    extra_tokens: int,
) -> list[BaseMessage]:
    """Shrink recent text until the packet fits, without truncating the current user turn."""
    packet_tokens = count_llm_request_tokens(prepared, tools, model_name)
    if packet_tokens <= input_working:
        return prepared

    prepared = _trim_preserving_current_user(prepared, trim_config, model_name)
    packet_tokens = count_llm_request_tokens(prepared, tools, model_name)
    if packet_tokens <= input_working:
        return prepared

    can_compact = compaction.enabled and isolated_llm is not None
    keep = compaction.keep_recent_messages
    if can_compact:
        while packet_tokens > input_working:
            next_keep = _smaller_keep_recent(keep)
            if next_keep is None:
                break
            logger.debug(CONTEXT_REFIT_LOG, next_keep, packet_tokens, input_working)
            prepared = await compact_messages(
                prepared,
                isolated_llm,
                config=_compaction_config(request, keep_recent_messages=next_keep),
                model_name=model_name,
                extra_tokens=extra_tokens,
                force=True,
            )
            prepared = drop_old_tool_results(prepared, keep_recent=0)
            prepared = _trim_preserving_current_user(prepared, trim_config, model_name)
            keep = next_keep
            packet_tokens = count_llm_request_tokens(prepared, tools, model_name)

        if packet_tokens > input_working:
            logger.debug(CONTEXT_REFIT_LOG, 1, packet_tokens, input_working)
            prepared = await compact_leaving_current_user(
                prepared,
                isolated_llm,
                config=_compaction_config(request, keep_recent_messages=1),
                model_name=model_name,
                extra_tokens=extra_tokens,
            )
            prepared = drop_old_tool_results(prepared, keep_recent=0)
            prepared = _trim_preserving_current_user(prepared, trim_config, model_name)
            packet_tokens = count_llm_request_tokens(prepared, tools, model_name)

    if packet_tokens > input_working:
        prepared = _irreducible_core(prepared)
    return prepared


def _raise_if_core_exceeds(
    prepared: list[BaseMessage],
    *,
    tools: Iterable[Any] | None,
    input_working: int,
    model_name: str,
) -> list[BaseMessage]:
    core = _irreducible_core(prepared)
    core_tokens = count_llm_request_tokens(core, tools, model_name)
    if core_tokens > input_working:
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

    packet_tokens = count_llm_request_tokens(prepared, tools, model_name)
    if packet_tokens > input_working:
        logger.warning(CONTEXT_COLLAPSED_TO_CORE_LOG, packet_tokens, core_tokens, input_working)
        return core
    return prepared


async def prepare_messages_for_llm(
    messages: list[BaseMessage],
    *,
    request: BasicLLMRequest,
    isolated_llm,
    tools: Iterable[Any] | None = None,
    force_compact: bool = False,
) -> list[BaseMessage]:
    """Apply single-message trim, then compaction; fail if the core still cannot fit."""

    model_name = str(getattr(request, "model", "") or "gpt-4o")
    trim_config = _as_trim_config(getattr(request, "message_trim_config", None))
    prepared = _trim_preserving_current_user(list(messages or []), trim_config, model_name)
    compaction = _compaction_config(request)
    tool_list = list(tools) if tools is not None else None
    extra_tokens = count_tool_schema_tokens(tool_list, model_name)
    if compaction.enabled and isolated_llm is not None and (force_compact or compaction.max_token_threshold > 0):
        prepared = await compact_messages(
            prepared,
            isolated_llm,
            config=compaction,
            model_name=model_name,
            extra_tokens=extra_tokens,
            force=force_compact,
        )

    input_working = _input_working_tokens(request)
    if input_working <= 0:
        return prepared

    prepared = _drop_tools_toward_budget(
        prepared,
        input_working=input_working,
        tools=tool_list,
        model_name=model_name,
        force_compact=force_compact,
    )
    prepared = await _refit_packet_to_working_budget(
        prepared,
        request=request,
        isolated_llm=isolated_llm,
        tools=tool_list,
        model_name=model_name,
        trim_config=trim_config,
        compaction=compaction,
        input_working=input_working,
        extra_tokens=extra_tokens,
    )
    return _raise_if_core_exceeds(
        prepared,
        tools=tool_list,
        input_working=input_working,
        model_name=model_name,
    )
