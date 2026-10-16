"""长连接上的智能体执行：只把最终回答正文推回会话。"""

from __future__ import annotations

import asyncio

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.services.skill_channel_aibot_long_connection import AnswerRequest, visible_answer_delta

_CANCEL_POLL_SECONDS = 0.05

ANSWER_FAILED_LOG_TEMPLATE = "event=wecom_aibot_long_connection_answer_failed channel_id=%s failed_stage=run_agent error_type=%s"


def run_long_connection_answer(request: AnswerRequest) -> None:
    """在后台线程里跑现有智能体流，正文增量交给连接会话节流。"""
    import threading

    threading.Thread(
        target=_run_guarded,
        args=(request,),
        name=f"wecom-aibot-{request.channel.id}",
        daemon=True,
    ).start()


def _run_guarded(request: AnswerRequest) -> None:
    from django.db import close_old_connections

    close_old_connections()
    try:
        _run(request)
    except Exception as exc:
        proxy = RuntimeError(type(exc).__name__)
        proxy.__traceback__ = exc.__traceback__
        logger.error(
            ANSWER_FAILED_LOG_TEMPLATE,
            request.channel.id,
            type(exc).__name__,
            exc_info=(type(proxy), proxy, proxy.__traceback__),
        )
        request.fail()
    finally:
        close_old_connections()


def user_visible_failure(event: dict) -> str | None:
    """智能体流里已经展示给用户的失败说明。没有这句时由会话回落到渠道固定文案。"""
    if not isinstance(event, dict) or event.get("type") not in {"ERROR", "RUN_ERROR"}:
        return None
    text = event.get("error") or event.get("message") or ""
    if not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


async def _aclose_stream(stream) -> None:
    close = getattr(stream, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        logger.debug("event=wecom_aibot_long_connection_stream_close_ignored")


def _run(request: AnswerRequest) -> None:
    from apps.opspilot.services.skill_channel_chat_service import (
        _history_from_conversation,
        build_skill_chat_params,
        get_or_create_conversation,
        parse_sse_json_payloads,
    )
    from apps.opspilot.services.skill_memory_service import inject_skill_memory_prompt
    from apps.opspilot.utils.agui_chat import _generate_agui_stream

    channel = request.channel
    skill = channel.skill
    conversation = get_or_create_conversation(channel, request.external_user_id, request.session_id or None)
    request_user = type("IMUser", (), {"username": request.external_user_id or "", "id": None, "locale": "en"})()
    params = build_skill_chat_params(skill, request.user_message, request_user)
    inject_skill_memory_prompt(params, skill, request.external_user_id, request.user_message)
    params["reply_language"] = "match_user"
    params["chat_history"] = _history_from_conversation(conversation, skill.conversation_window_size or 10)
    params["skill_session_id"] = conversation.session_id
    params["show_think"] = False
    final_stats = {
        "content": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "llm_call_count": 0,
        "usage_calls": [],
    }

    stream = _generate_agui_stream(
        params,
        skill.name,
        skill.skill_type,
        False,
        final_stats,
        {},
        "",
        request.user_message,
        skill.id,
        None,
    )

    async def consume():
        text = ""
        failure = None

        async def pump():
            nonlocal text, failure
            async for line in stream:
                if request.cancelled:
                    return
                piece = line.decode("utf-8") if isinstance(line, (bytes, bytearray)) else str(line)
                for event in parse_sse_json_payloads(piece):
                    visible = user_visible_failure(event)
                    if visible:
                        failure = visible
                        return
                    delta = visible_answer_delta(event)
                    if delta:
                        text += delta
                        request.publish(text)

        worker = asyncio.create_task(pump())
        try:
            while not worker.done():
                if request.cancelled:
                    worker.cancel()
                    break
                await asyncio.sleep(_CANCEL_POLL_SECONDS)
            try:
                await worker
            except asyncio.CancelledError:
                if not request.cancelled:
                    raise
        finally:
            await _aclose_stream(stream)
        return failure

    failure = asyncio.run(consume())
    if request.cancelled:
        return
    if failure:
        request.fail(failure)
        return
    request.finish()
