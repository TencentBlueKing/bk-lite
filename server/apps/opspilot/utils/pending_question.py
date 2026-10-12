"""终止式提问的会话续接标记。

发出选择后本轮结束。下一轮用 conversation_key 取回证据并立即删除标记。
存储使用 Django cache，不新增表。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from django.core.cache import cache
from langchain_core.load import dumpd, load
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.prepare_llm_context import drop_old_tool_results

PENDING_QUESTION_PREFIX = "opspilot:pending_question"
K8S_ANALYSIS_STASH_PREFIX = "opspilot:k8s_analysis_detail"
PENDING_QUESTION_TTL_SECONDS = 30 * 60
KIND_USER_CHOICE = "user_choice"
KIND_LIMIT_CONTINUE = "limit_continue"
KIND_K8S_REPAIR_MODE = "k8s_repair_mode"
PENDING_KINDS = frozenset({KIND_USER_CHOICE, KIND_LIMIT_CONTINUE, KIND_K8S_REPAIR_MODE})

_SAVED_LOG = "event=pending_question_saved conversation_key=%s kind=%s evidence_tokens=%s"
_HIT_LOG = "event=pending_question_hit conversation_key=%s kind=%s evidence_tokens=%s"
_EXPIRED_LOG = "event=pending_question_expired conversation_key=%s kind=%s evidence_tokens=%s"


def resolve_conversation_key(
    *,
    bot_id: Any = None,
    session_id: Any = None,
    thread_id: Any = None,
    skill_session_id: Any = None,
    conversation_key: Any = None,
) -> str:
    """把四个入口的会话标识归一成一个 key。缺标识时返回空串。"""
    explicit = str(conversation_key or "").strip()
    if explicit:
        return explicit
    skill_session = str(skill_session_id or "").strip()
    if skill_session:
        return f"skill:{skill_session}"
    bot = str(bot_id or "").strip()
    session = str(session_id or "").strip()
    if bot and session:
        return f"flow:{bot}:{session}"
    thread = str(thread_id or "").strip()
    if thread:
        return f"thread:{thread}"
    if session:
        return f"session:{session}"
    return ""


def resolve_conversation_key_from_mapping(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    graph_request = source.get("graph_request")
    extra = {}
    if graph_request is not None:
        raw_extra = getattr(graph_request, "extra_config", None) or {}
        if isinstance(raw_extra, dict):
            extra = raw_extra
    return resolve_conversation_key(
        conversation_key=source.get("conversation_key") or extra.get("conversation_key"),
        bot_id=source.get("bot_id") or extra.get("bot_id"),
        session_id=source.get("session_id") or extra.get("session_id"),
        thread_id=source.get("thread_id") or getattr(graph_request, "thread_id", None) or extra.get("thread_id"),
        skill_session_id=source.get("skill_session_id") or extra.get("skill_session_id"),
    )


def _cache_key(conversation_key: str) -> str:
    return f"{PENDING_QUESTION_PREFIX}:{conversation_key}"


def _evidence_tokens(messages: list[Any] | None) -> int:
    text = []
    for message in messages or []:
        if isinstance(message, dict):
            text.append(str(message.get("content") or message.get("kwargs", {}).get("content") or ""))
        else:
            text.append(str(getattr(message, "content", "") or ""))
    return len("".join(text)) // 4


def _created_at_ms(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("created_at") or 0)
    except (TypeError, ValueError):
        return 0


def _is_expired(payload: dict[str, Any], *, now_ms: int | None = None) -> bool:
    created = _created_at_ms(payload)
    if created <= 0:
        return False
    current = int(now_ms if now_ms is not None else time.time() * 1000)
    return current - created > PENDING_QUESTION_TTL_SECONDS * 1000


def collect_evidence_messages(messages: list[Any] | None) -> list[BaseMessage]:
    """只保留当前用户消息之后的 AI tool_calls 与 ToolMessage。"""
    items = list(messages or [])
    last_human = -1
    for index, message in enumerate(items):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            last_human = index
    current = items[last_human + 1 :] if last_human >= 0 else items
    evidence: list[BaseMessage] = []
    for message in current:
        tool_calls = getattr(message, "tool_calls", None) or []
        message_type = str(getattr(message, "type", "") or "")
        if tool_calls and message_type in {"ai", "AIMessage"}:
            evidence.append(message)
            continue
        if isinstance(message, ToolMessage) or message_type == "tool":
            evidence.append(message)
    return drop_old_tool_results(evidence)


def serialize_evidence(messages: list[Any] | None) -> list[dict[str, Any]]:
    serialized = []
    for message in messages or []:
        if isinstance(message, BaseMessage):
            serialized.append(dumpd(message))
    return serialized


def deserialize_evidence(raw: Any) -> list[BaseMessage]:
    if not isinstance(raw, list):
        return []
    messages: list[BaseMessage] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        loaded = load(item)
        if isinstance(loaded, BaseMessage):
            messages.append(loaded)
    return messages


def format_choice_text(question: str, question_type: str, options: list[Any] | None) -> str:
    """问题加编号选项。confirm 固定为是/否，text 只有问题。"""
    title = str(question or "").strip()
    if question_type == "text":
        return title
    if question_type == "confirm":
        labels = ["是", "否"]
    else:
        labels = []
        for option in options or []:
            if isinstance(option, dict):
                label = str(option.get("label") or option.get("key") or "").strip()
            else:
                label = str(option or "").strip()
            if label:
                labels.append(label)
    if not labels:
        return title
    lines = [title, ""] if title else []
    lines.extend(f"{index}. {label}" for index, label in enumerate(labels, start=1))
    return "\n".join(lines).strip()


def choice_options(question_type: str, options: list[Any] | None) -> tuple[list[dict[str, Any]], bool]:
    if question_type == "confirm":
        return (
            [
                {"key": "yes", "label": "是", "description": "", "recommended": False},
                {"key": "no", "label": "否", "description": "", "recommended": False},
            ],
            False,
        )
    if question_type == "text":
        return [], False
    normalized = []
    for option in options or []:
        if isinstance(option, dict):
            label = str(option.get("label") or option.get("key") or "").strip()
        else:
            label = str(option or "").strip()
        if label:
            normalized.append({"key": label, "label": label, "description": "", "recommended": False})
    return normalized, question_type == "multi_select"


def build_choice_request(
    *,
    question: str,
    question_type: str,
    options: list[Any] | None,
    execution_id: str,
    node_id: str,
    description: str = "",
) -> dict[str, Any]:
    from apps.opspilot.metis.llm.chain.report_renderers.k8s import build_a2ui_report_contract

    options_data, multiple = choice_options(question_type, options)
    return {
        "execution_id": execution_id,
        "node_id": node_id,
        "choice_id": uuid.uuid4().hex[:8],
        "a2ui": build_a2ui_report_contract(
            component="user-choice",
            event_name="user_choice_request",
            actions=[],
        ),
        "title": question,
        "description": description,
        "options": options_data,
        "multiple": multiple,
        "min_select": 1 if options_data else 0,
        "max_select": len(options_data) if multiple else (1 if options_data else 0),
        "display_hint": "text" if question_type == "text" else "auto",
    }


def save_pending_question(
    conversation_key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    key = str(conversation_key or "").strip()
    if not key:
        return None
    kind = str(payload.get("kind") or "")
    if kind not in PENDING_KINDS:
        return None
    evidence = payload.get("evidence_messages") or []
    stored = {
        "kind": kind,
        "execution_id": str(payload.get("execution_id") or ""),
        "node_id": str(payload.get("node_id") or ""),
        "question": str(payload.get("question") or ""),
        "options": list(payload.get("options") or []),
        "question_text": str(payload.get("question_text") or ""),
        "evidence_messages": evidence if isinstance(evidence, list) else [],
        "k8s_analysis": payload.get("k8s_analysis"),
        "created_at": int(payload.get("created_at") or time.time() * 1000),
    }
    cache.set(_cache_key(key), stored, PENDING_QUESTION_TTL_SECONDS)
    logger.info(_SAVED_LOG, key, kind, _evidence_tokens(stored["evidence_messages"]))
    return stored


def peek_pending_question(conversation_key: str) -> dict[str, Any] | None:
    key = str(conversation_key or "").strip()
    if not key:
        return None
    payload = cache.get(_cache_key(key))
    if not isinstance(payload, dict):
        return None
    if _is_expired(payload):
        cache.delete(_cache_key(key))
        logger.info(_EXPIRED_LOG, key, payload.get("kind") or "", _evidence_tokens(payload.get("evidence_messages")))
        return None
    return payload


def consume_pending_question(conversation_key: str) -> dict[str, Any] | None:
    """读取后立即删除。过期与未命中都返回 None。"""
    key = str(conversation_key or "").strip()
    if not key:
        return None
    payload = peek_pending_question(key)
    if payload is None:
        return None
    cache.delete(_cache_key(key))
    logger.info(_HIT_LOG, key, payload.get("kind") or "", _evidence_tokens(payload.get("evidence_messages")))
    return payload


def splice_evidence_messages(
    messages: list[BaseMessage],
    evidence: list[BaseMessage],
    question_text: str,
) -> list[BaseMessage]:
    """把证据插到提问文本之前，使顺序与未被打断时一致。"""
    if not evidence:
        return list(messages or [])
    target = str(question_text or "").strip()
    insert_at = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, AIMessage) and getattr(message, "type", "") != "ai":
            continue
        content = str(getattr(message, "content", "") or "")
        if target and target in content:
            insert_at = index
            break
        if not target:
            insert_at = index
            break
    return list(messages[:insert_at]) + list(evidence) + list(messages[insert_at:])


def is_choice_prompt_text(text: str) -> bool:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if any(line.startswith("1.") or line.startswith("1、") for line in lines):
        return True
    return False


def messages_include_terminal_choice(messages: list[Any] | None) -> bool:
    """本步已经向用户发出选择，外层不应再总结或进入后续步骤。"""
    for message in messages or []:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            if str(name or "") == "request_user_choice":
                return True
        if str(getattr(message, "name", "") or "") == "request_user_choice":
            return True
        if is_choice_prompt_text(str(getattr(message, "content", "") or "")):
            return True
    return False


def is_answer_after_choice_prompt(messages: list[Any] | None) -> bool:
    """上一条助手是提问文本，本条用户消息是回答。"""
    items = list(messages or [])
    last_human = -1
    for index, message in enumerate(items):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            last_human = index
    if last_human <= 0:
        return False
    for message in reversed(items[:last_human]):
        message_type = str(getattr(message, "type", "") or "")
        if message_type in {"tool", "system"} or isinstance(message, ToolMessage):
            continue
        if message_type not in {"ai", "AIMessage"} and not isinstance(message, AIMessage):
            return False
        return is_choice_prompt_text(str(getattr(message, "content", "") or ""))
    return False


def store_k8s_analysis_details(execution_id: str, deployments: list[Any]) -> None:
    execution = str(execution_id or "").strip()
    if not execution:
        return
    cache.set(f"{K8S_ANALYSIS_STASH_PREFIX}:{execution}", list(deployments or []), PENDING_QUESTION_TTL_SECONDS)


def take_k8s_analysis_details(execution_id: str) -> list[Any]:
    execution = str(execution_id or "").strip()
    if not execution:
        return []
    key = f"{K8S_ANALYSIS_STASH_PREFIX}:{execution}"
    details = cache.get(key)
    cache.delete(key)
    return list(details) if isinstance(details, list) else []
