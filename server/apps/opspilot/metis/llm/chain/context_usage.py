"""Bounded token breakdown of the next LLM packet for the chat usage ring."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from apps.opspilot.metis.llm.chain.compaction import SUMMARY_HUMAN_PREFIX
from apps.opspilot.metis.llm.chain.token_utils import count_llm_request_tokens, count_message_tokens, count_text_tokens, count_tool_schema_tokens

CONTEXT_USAGE_EVENT = "llm_context_usage"
SEGMENT_IDS = ("system", "tools", "skills", "wiki", "summary", "conversation")
_WIKI_MARKER = "【相关知识库信息】"
_SKILL_MARKER = "【技能包执行】"
_SPLIT_MARKERS: tuple[tuple[str, str], ...] = (
    ("wiki", _WIKI_MARKER),
    ("skills", _SKILL_MARKER),
)


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "") or ""))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    return str(content or "")


def _int_field(raw: Any, default: int = 0) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(value, 0)


def _request_int(request: Any, attr: str, extra_key: str = "") -> int:
    extra = getattr(request, "extra_config", None) or {}
    if extra_key:
        extra_value = extra.get(extra_key) if isinstance(extra, dict) else None
        if extra_value is not None:
            return _int_field(extra_value)
    return _int_field(getattr(request, attr, 0))


def _split_system_text(text: str, model_name: str) -> dict[str, int]:
    hits: list[tuple[int, str]] = []
    for segment_id, marker in _SPLIT_MARKERS:
        index = text.find(marker)
        if index >= 0:
            hits.append((index, segment_id))
    hits.sort()
    parts: dict[str, int] = {"system": 0, "wiki": 0, "skills": 0}
    if not hits:
        parts["system"] = count_text_tokens(text, model_name) if text else 0
        return parts

    first_start = hits[0][0]
    parts["system"] = count_text_tokens(text[:first_start], model_name) if first_start > 0 else 0
    for offset, (start, segment_id) in enumerate(hits):
        end = hits[offset + 1][0] if offset + 1 < len(hits) else len(text)
        slice_text = text[start:end]
        if slice_text:
            parts[segment_id] = parts.get(segment_id, 0) + count_text_tokens(slice_text, model_name)
    return parts


def _is_summary_message(message: BaseMessage) -> bool:
    if not isinstance(message, HumanMessage):
        return False
    return _message_text(message).startswith(SUMMARY_HUMAN_PREFIX)


def _is_skill_message(message: BaseMessage) -> bool:
    if isinstance(message, SystemMessage) or _is_summary_message(message):
        return False
    return _SKILL_MARKER in _message_text(message)[:200]


def summarize_llm_context_usage(
    messages: Sequence[BaseMessage],
    *,
    request: Any,
    tools: Iterable[Any] | None = None,
    model_name: str = "gpt-4o",
) -> dict[str, Any] | None:
    """Return a bounded usage snapshot of the packet that will be sent. None if no budget."""
    extra = getattr(request, "extra_config", None) or {}
    window_tokens = _int_field(extra.get("context_window_tokens") if isinstance(extra, dict) else None)
    input_working = _request_int(request, "input_working_tokens", "input_working_tokens")
    compaction_threshold = _int_field(getattr(request, "compaction_max_token_threshold", 0))
    if input_working <= 0:
        input_working = window_tokens
    if input_working <= 0:
        return None

    tool_list = list(tools) if tools is not None else None
    packet_tokens = count_llm_request_tokens(list(messages or []), tool_list, model_name)
    system_messages = [message for message in messages or [] if isinstance(message, SystemMessage)]
    system_text = "\n\n".join(_message_text(message) for message in system_messages)
    split = _split_system_text(system_text, model_name)

    counts: dict[str, int] = {segment_id: 0 for segment_id in SEGMENT_IDS}
    counts["system"] = split["system"]
    counts["wiki"] = split["wiki"]
    counts["skills"] = split["skills"]
    counts["tools"] = count_tool_schema_tokens(tool_list, model_name)

    compacted = False
    for message in messages or []:
        if isinstance(message, SystemMessage):
            continue
        tokens = count_message_tokens([message], model_name)
        if _is_summary_message(message):
            counts["summary"] += tokens
            compacted = True
            continue
        if _is_skill_message(message):
            counts["skills"] += tokens
            continue
        counts["conversation"] += tokens

    assigned = sum(counts.values())
    if packet_tokens > assigned:
        counts["conversation"] += packet_tokens - assigned

    segments = [{"id": segment_id, "tokens": counts[segment_id]} for segment_id in SEGMENT_IDS if counts[segment_id] > 0]
    return {
        "packet_tokens": packet_tokens,
        "input_working_tokens": input_working,
        "window_tokens": window_tokens,
        "compaction_threshold_tokens": compaction_threshold,
        "compacted": compacted,
        "segments": segments,
    }
