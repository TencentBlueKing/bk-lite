"""request_user_choice 发出即结束本轮。校验失败时不终止，交给工具返回拒绝理由。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.messages import AIMessage, ToolMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.chain.nested_stream import publish_owned_custom_event_nowait
from apps.opspilot.metis.llm.tools.common.user_choice_guard import validate_user_choice_options
from apps.opspilot.metis.llm.tools.kubernetes.user_choice_guard import build_kubernetes_cluster_choice_guard
from apps.opspilot.utils.pending_question import (
    KIND_USER_CHOICE,
    build_choice_request,
    collect_evidence_messages,
    format_choice_text,
    resolve_conversation_key_from_mapping,
    save_pending_question,
    serialize_evidence,
)

_CHOICE_TOOL = "request_user_choice"
_TERMINAL_TOOL_RESULT = "已向用户发出选择，本轮结束。用户回答后会在新一轮带着已有结果继续。"


def _configurable(runtime: Any) -> dict[str, Any]:
    config = getattr(runtime, "config", None)
    if not isinstance(config, dict):
        config = {}
    configurable = config.get("configurable") if isinstance(config, dict) else None
    return dict(configurable) if isinstance(configurable, dict) else {}


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_call_args(call: Any) -> dict[str, Any]:
    if isinstance(call, dict):
        args = call.get("args") or {}
    else:
        args = getattr(call, "args", None) or {}
    return dict(args) if isinstance(args, dict) else {}


def _tool_call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "")
    return str(getattr(call, "id", "") or "")


def _choice_calls(message: Any) -> list[Any]:
    return [call for call in (getattr(message, "tool_calls", None) or []) if _tool_call_name(call) == _CHOICE_TOOL]


def guard_rejection(call: Any, configurable: dict[str, Any]) -> str:
    args = _tool_call_args(call)
    question = str(args.get("question") or "")
    question_type = str(args.get("question_type") or "")
    options = args.get("options")
    guard = build_kubernetes_cluster_choice_guard(
        question=question,
        options=options if isinstance(options, list) else None,
        configurable=configurable,
    )
    return validate_user_choice_options(
        question_type=question_type,
        options=options if isinstance(options, list) else None,
        guard=guard,
    )


def emit_choice_request(config: Any, payload: dict[str, Any]) -> None:
    if publish_owned_custom_event_nowait(config, "user_choice_request", payload):
        return
    try:
        dispatch_custom_event("user_choice_request", payload, config=config)
    except Exception as exc:
        logger.debug("user_choice_request 派发跳过: %s", exc)


def finalize_user_choice(
    *,
    question: str,
    question_type: str,
    options: list[Any] | None,
    config: Any,
    messages: list[Any],
    tool_call_id: str,
    kind: str = KIND_USER_CHOICE,
    description: str = "",
    k8s_analysis: dict[str, Any] | None = None,
    extra_evidence: list[Any] | None = None,
) -> tuple[str, AIMessage]:
    configurable = {}
    if isinstance(config, dict):
        raw = config.get("configurable")
        if isinstance(raw, dict):
            configurable = raw
    execution_id = str(configurable.get("execution_id") or "")
    node_id = str(configurable.get("node_id") or "skill_test")
    request_payload = build_choice_request(
        question=question,
        question_type=question_type,
        options=options,
        execution_id=execution_id,
        node_id=node_id,
        description=description,
    )
    question_text = format_choice_text(question, question_type, request_payload["options"])
    emit_choice_request(config, request_payload)
    evidence = collect_evidence_messages(messages)
    if extra_evidence:
        evidence = list(evidence) + list(extra_evidence)
    tool_message = ToolMessage(content=_TERMINAL_TOOL_RESULT, tool_call_id=tool_call_id or request_payload["choice_id"], name=_CHOICE_TOOL)
    evidence.append(tool_message)
    conversation_key = resolve_conversation_key_from_mapping(configurable)
    save_pending_question(
        conversation_key,
        {
            "kind": kind,
            "execution_id": execution_id,
            "node_id": node_id,
            "question": question,
            "options": request_payload["options"],
            "question_text": question_text,
            "evidence_messages": serialize_evidence(evidence),
            "k8s_analysis": k8s_analysis,
        },
    )
    return question_text, tool_message


class TerminalUserChoiceMiddleware(AgentMiddleware):
    """模型调用 request_user_choice 且校验通过时结束本轮。"""

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        return self._maybe_terminate(state, runtime)

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        return self._maybe_terminate(state, runtime)

    def _maybe_terminate(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages:
            return None
        last = messages[-1]
        calls = _choice_calls(last)
        if not calls:
            return None
        configurable = _configurable(runtime)
        config = getattr(runtime, "config", None)
        for call in calls:
            rejection = guard_rejection(call, configurable)
            if rejection:
                logger.info("event=user_choice_guard_rejected node_id=%s", configurable.get("node_id") or "")
                return None
        call = calls[0]
        args = _tool_call_args(call)
        question_text, tool_message = finalize_user_choice(
            question=str(args.get("question") or ""),
            question_type=str(args.get("question_type") or "single_select"),
            options=args.get("options") if isinstance(args.get("options"), list) else None,
            config=config if isinstance(config, dict) else {"configurable": configurable},
            messages=messages[:-1],
            tool_call_id=_tool_call_id(call),
        )
        return {
            "jump_to": "end",
            "messages": [tool_message, AIMessage(content=question_text)],
        }
