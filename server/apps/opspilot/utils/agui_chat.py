"""
AGUI协议聊天流式处理模块

实现AGUI(Agent UI)协议规范的流式聊天功能
"""

import json
import logging
import re
import threading
import time

from django.http import StreamingHttpResponse

from apps.opspilot.models import LLMModel, SkillRequestLog
from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.utils.agent_factory import create_agent_instance, create_sse_response_headers
from apps.opspilot.utils.execution_interrupt import is_interrupt_requested
from apps.opspilot.utils.sse_chat import _process_think_content, _split_think_content

logger = logging.getLogger(__name__)


def _sanitize_think_tag_residue(content: str, show_think: bool) -> str:
    """移除残余 think 标签，兜底处理孤立的 <think>/</think> 输出"""
    if show_think or not content:
        return content
    return content.replace("<think>", "").replace("</think>", "")


def _strip_post_tool_meta_preamble(content: str) -> str:
    """移除工具结果后的第一句桥接型自述内容"""
    if not content:
        return content

    meta_preamble_pattern = re.compile(
        r"^\s*(?:好的[，,\s]*|好[的吧]?[，,\s]*|OK[,\s]*|Okay[,\s]*)?"
        r"(?:我已经(?:成功)?获取(?:到|到了)|我已(?:经)?获取(?:到|到了)|现在我需要|接下来(?:我)?(?:需要|将)|"
        r"根据工具结果|根据返回结果|工具(?:已经)?返回了?|我现在可以|我将根据|"
        r"I have (?:retrieved|fetched)|Now I need to|Next I(?:'ll| will)|According to the tool result|The tool returned)"
        r"[^\n。！？!?]*(?:[。！？!?]|\n|$)\s*",
        re.IGNORECASE,
    )
    stripped = meta_preamble_pattern.sub("", content, count=1)
    return stripped.lstrip()


def _extract_post_tool_meta_preamble(content: str) -> tuple[str, str]:
    """提取工具结果后的第一句桥接型自述内容，返回(前缀, 剩余正文)"""
    if not content:
        return "", content

    meta_preamble_pattern = re.compile(
        r"^\s*(?:好的[，,\s]*|好[的吧]?[，,\s]*|OK[,\s]*|Okay[,\s]*)?"
        r"(?:我已经(?:成功)?获取(?:到|到了)|我已(?:经)?获取(?:到|到了)|现在我需要|接下来(?:我)?(?:需要|将)|"
        r"根据工具结果|根据返回结果|工具(?:已经)?返回了?|我现在可以|我将根据|"
        r"I have (?:retrieved|fetched)|Now I need to|Next I(?:'ll| will)|According to the tool result|The tool returned)"
        r"[^\n。！？!?]*(?:[。！？!?]|\n|$)\s*",
        re.IGNORECASE,
    )
    match = meta_preamble_pattern.match(content)
    if not match:
        return "", content
    return match.group(0), content[match.end() :].lstrip()


def _build_thinking_event(delta: str, timestamp: int | None = None) -> dict:
    """构建自定义 THINKING 事件"""
    return {
        "type": "THINKING",
        "delta": delta,
        "timestamp": timestamp or int(time.time() * 1000),
    }


def _supports_thinking_events(request) -> bool:
    model_name = getattr(request, "model", "") or ""
    return "qwen" in model_name.lower()


def _build_sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _init_agui_stream_state() -> dict:
    return {
        "think_buffer": "",
        "in_think_block": False,
        "is_first_content": True,
        "has_think_tags": True,
        "active_message_id": None,
        "pending_content_events": [],
        "buffer_pre_tool_content": False,
        "post_tool_result_seen": False,
        "emit_pending_as_thinking": False,
        "pending_phase": None,
    }


def _flush_pending_content_events(state: dict, strip_post_tool_preamble: bool = False) -> list[str]:
    pending_content_events = state["pending_content_events"]
    if not pending_content_events:
        return []

    if strip_post_tool_preamble:
        combined_content = "".join(event.get("delta", "") for event in pending_content_events)
        stripped_content = _strip_post_tool_meta_preamble(combined_content)
        if stripped_content != combined_content:
            template_event = pending_content_events[-1]
            pending_content_events.clear()
            if not stripped_content:
                return []
            return [_build_sse_line({**template_event, "delta": stripped_content})]

    lines = [_build_sse_line(pending_event) for pending_event in pending_content_events]
    pending_content_events.clear()
    return lines


def _flush_pending_content_as_thinking(state: dict) -> list[str]:
    pending_content_events = state["pending_content_events"]
    if not pending_content_events:
        return []
    combined_content = "".join(event.get("delta", "") for event in pending_content_events)
    pending_content_events.clear()
    if not combined_content.strip():
        return []
    return [_build_sse_line(_build_thinking_event(combined_content))]


def _flush_post_tool_pending_content_split(state: dict) -> list[str]:
    pending_content_events = state["pending_content_events"]
    if not pending_content_events:
        return []
    combined_content = "".join(event.get("delta", "") for event in pending_content_events)
    template_event = pending_content_events[-1]
    pending_content_events.clear()
    meta_prefix, visible_content = _extract_post_tool_meta_preamble(combined_content)
    lines = []
    if meta_prefix.strip():
        lines.append(_build_sse_line(_build_thinking_event(meta_prefix)))
    if visible_content.strip():
        lines.append(_build_sse_line({**template_event, "delta": visible_content}))
    return lines


def _handle_text_message_content_event(data_json: dict, state: dict, show_think: bool, enable_thinking_split: bool) -> tuple[str, list[str]]:
    content_chunk = data_json.get("delta", "")
    thinking_content = ""

    if show_think and enable_thinking_split:
        (
            output_content,
            thinking_content,
            state["think_buffer"],
            state["in_think_block"],
            state["is_first_content"],
            state["has_think_tags"],
        ) = _split_think_content(
            content_chunk,
            state["think_buffer"],
            state["in_think_block"],
            state["is_first_content"],
            state["has_think_tags"],
        )
    else:
        (
            output_content,
            state["think_buffer"],
            state["in_think_block"],
            state["is_first_content"],
            state["has_think_tags"],
        ) = _process_think_content(
            content_chunk,
            state["think_buffer"],
            state["in_think_block"],
            state["is_first_content"],
            show_think,
            state["has_think_tags"],
        )

    output_content = _sanitize_think_tag_residue(output_content, show_think)
    thinking_content = _sanitize_think_tag_residue(thinking_content, show_think)

    immediate_lines = []
    if show_think and enable_thinking_split and thinking_content:
        immediate_lines.append(_build_sse_line(_build_thinking_event(thinking_content, data_json.get("timestamp"))))

    if not output_content:
        return "", immediate_lines

    data_json["delta"] = output_content
    if state["buffer_pre_tool_content"] and data_json.get("message_id") == state["active_message_id"]:
        state["pending_content_events"].append(data_json.copy())
        return "", immediate_lines

    return _build_sse_line(data_json), immediate_lines


def _handle_tool_transition_event(event_type: str, data_json: dict, state: dict, show_think: bool, enable_thinking_split: bool) -> list[str]:
    logger.info(
        "[AGUI Chat] tool transition event: type=%s, tool_name=%s, tool_call_id=%s, parent_message_id=%s",
        event_type,
        data_json.get("tool_name"),
        data_json.get("tool_call_id"),
        data_json.get("parent_message_id"),
    )
    if event_type == "TOOL_CALL_START":
        parent_message_id = data_json.get("parent_message_id")
        if state["buffer_pre_tool_content"] and parent_message_id == state["active_message_id"]:
            lines = _flush_pending_content_as_thinking(state) if state["emit_pending_as_thinking"] else []
            if not state["emit_pending_as_thinking"]:
                state["pending_content_events"].clear()
            state["buffer_pre_tool_content"] = False
            return lines
        return []

    state["buffer_pre_tool_content"] = True
    state["emit_pending_as_thinking"] = show_think and enable_thinking_split
    if event_type == "TOOL_CALL_RESULT":
        state["post_tool_result_seen"] = True
        state["pending_phase"] = "post_tool"
    return []


def _handle_text_message_end_event(data_json: dict, state: dict, show_think: bool, enable_thinking_split: bool) -> list[str]:
    lines = []
    if not show_think and not state["in_think_block"] and state["think_buffer"]:
        safe_buffer = _sanitize_think_tag_residue(state["think_buffer"], show_think)
        state["think_buffer"] = ""
        if safe_buffer:
            if state["buffer_pre_tool_content"] and data_json.get("message_id") == state["active_message_id"]:
                state["pending_content_events"].append(
                    {
                        "type": "TEXT_MESSAGE_CONTENT",
                        "message_id": data_json.get("message_id"),
                        "delta": safe_buffer,
                        "timestamp": data_json.get("timestamp", int(time.time() * 1000)),
                    }
                )
            else:
                lines.append(
                    _build_sse_line(
                        {
                            "type": "TEXT_MESSAGE_CONTENT",
                            "message_id": data_json.get("message_id"),
                            "delta": safe_buffer,
                            "timestamp": data_json.get("timestamp", int(time.time() * 1000)),
                        }
                    )
                )

    if state["buffer_pre_tool_content"] and data_json.get("message_id") == state["active_message_id"]:
        if state["emit_pending_as_thinking"] and state["pending_phase"] == "post_tool":
            lines.extend(_flush_post_tool_pending_content_split(state))
        elif state["emit_pending_as_thinking"]:
            lines.extend(_flush_pending_content_as_thinking(state))
        elif not show_think:
            lines.extend(_flush_pending_content_events(state, strip_post_tool_preamble=state["post_tool_result_seen"]))
        else:
            lines.extend(_flush_pending_content_events(state))

    if (
        not show_think
        and state["buffer_pre_tool_content"]
        and data_json.get("message_id") == state["active_message_id"]
        and not state["emit_pending_as_thinking"]
    ):
        lines.extend(_flush_pending_content_events(state, strip_post_tool_preamble=state["post_tool_result_seen"]))

    state["active_message_id"] = None
    state["buffer_pre_tool_content"] = False
    state["post_tool_result_seen"] = False
    state["emit_pending_as_thinking"] = False
    state["pending_phase"] = None
    return lines


def _handle_agui_data_event(data_json: dict, state: dict, show_think: bool, enable_thinking_split: bool) -> tuple[str, list[str]]:
    event_type = data_json.get("type")
    if event_type == "TEXT_MESSAGE_START":
        state["active_message_id"] = data_json.get("message_id")
        state["pending_content_events"].clear()
        state["buffer_pre_tool_content"] = True
        state["emit_pending_as_thinking"] = show_think and enable_thinking_split
        state["pending_phase"] = "post_tool" if state["post_tool_result_seen"] else "pre_tool"
        return _build_sse_line(data_json), []

    if event_type in {"THINKING_TEXT_MESSAGE_START", "THINKING_TEXT_MESSAGE_END"}:
        return "", []

    if event_type == "THINKING_TEXT_MESSAGE_CONTENT":
        return (
            _build_sse_line(_build_thinking_event(data_json.get("delta", ""), data_json.get("timestamp"))),
            [],
        )

    if event_type == "TEXT_MESSAGE_CONTENT":
        return _handle_text_message_content_event(data_json, state, show_think, enable_thinking_split)

    if event_type in {"TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_RESULT"}:
        return _build_sse_line(data_json), _handle_tool_transition_event(event_type, data_json, state, show_think, enable_thinking_split)

    if event_type == "TEXT_MESSAGE_END":
        return _build_sse_line(data_json), _handle_text_message_end_event(data_json, state, show_think, enable_thinking_split)

    return _build_sse_line(data_json), []


async def _generate_agui_stream(
    graph, request, skill_name, skill_type, show_think, final_stats, kwargs, current_ip, user_message, skill_id, history_log
):
    try:
        logger.info(f"[AGUI Chat] 开始异步流处理 - skill_name: {skill_name}, skill_type: {skill_type}, show_think: {show_think}")
        chunk_index = 0
        accumulated_content = []
        state = _init_agui_stream_state()
        enable_thinking_split = _supports_thinking_events(request)
        execution_id = (request.extra_config or {}).get("execution_id") or request.thread_id

        async for sse_line in graph.agui_stream(request):
            if execution_id and is_interrupt_requested(execution_id):
                interrupt_data = {"type": "INTERRUPTED", "error": "执行已中断", "execution_id": execution_id, "timestamp": int(time.time() * 1000)}
                yield _build_sse_line(interrupt_data)
                return
            output_line = sse_line
            immediate_lines = []
            if sse_line.startswith("data: "):
                try:
                    data_json = json.loads(sse_line[6:].strip())
                    output_line, immediate_lines = _handle_agui_data_event(data_json, state, show_think, enable_thinking_split)
                    accumulated_content.append(data_json)
                except (json.JSONDecodeError, ValueError):
                    pass

            for line in immediate_lines:
                chunk_index += 1
                yield line

            chunk_index += 1
            if output_line:
                yield output_line

        final_stats["content"] = accumulated_content
        if final_stats["content"]:

            def log_in_background():
                _log_and_update_tokens_agui(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log)

            threading.Thread(target=log_in_background, daemon=True).start()

    except Exception as e:
        logger.error(f"[AGUI Chat] async stream error: {e}", exc_info=True)
        error_data = {"type": "ERROR", "error": f"聊天错误: {str(e)}", "timestamp": int(time.time() * 1000)}
        yield _build_sse_line(error_data)


def _log_and_update_tokens_agui(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log=None):
    """
    记录AGUI协议的请求日志并更新token统计
    """
    try:
        final_content = final_stats.get("content", "")
        if not final_content:
            return

        # 创建或更新日志
        if history_log:
            history_log.completion_tokens = 0
            history_log.prompt_tokens = 0
            history_log.total_tokens = 0
            history_log.response = final_content
            history_log.save()
        else:
            # skill_id必须存在才能创建日志
            if not skill_id:
                logger.warning(f"AGUI log skipped: skill_id is None for skill_name={skill_name}")
                return

            # 构建response_detail，包含token统计和响应内容
            response_detail = {
                "completion_tokens": 0,
                "prompt_tokens": 0,
                "total_tokens": 0,
                "response": final_content,
            }

            # 构建request_detail，包含请求参数
            request_detail = {
                "skill_name": skill_name,
                "show_think": show_think,
                "kwargs": kwargs,
            }

            SkillRequestLog.objects.create(
                skill_id=skill_id,
                current_ip=current_ip or "0.0.0.0",
                state=True,
                request_detail=request_detail,
                response_detail=response_detail,
                user_message=user_message,
            )

        logger.info(f"AGUI log created/updated for skill: {skill_name}")
    except Exception as e:
        logger.error(f"AGUI log update error: {e}")


def stream_agui_chat(params, skill_name, kwargs, current_ip, user_message, skill_id=None, history_log=None):
    """
    AGUI协议的流式聊天主函数

    Args:
        params: 请求参数字典
        skill_name: 技能名称
        kwargs: 额外参数
        current_ip: 客户端IP
        user_message: 用户消息
        skill_id: 技能ID
        history_log: 历史日志对象

    Returns:
        StreamingHttpResponse: AGUI协议格式的流式响应
    """
    llm_model = LLMModel.objects.get(id=params["llm_model"])
    show_think = params.pop("show_think", True)
    skill_type = params.get("skill_type")
    params.pop("group", 0)
    params["execution_id"] = params.get("execution_id") or params.get("thread_id") or str(int(time.time() * 1000))

    chat_kwargs, doc_map, title_map = chat_service.format_chat_server_kwargs(params, llm_model)

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": []}
    graph, request = create_agent_instance(skill_type, chat_kwargs)
    response = StreamingHttpResponse(
        _generate_agui_stream(
            graph,
            request,
            skill_name,
            skill_type,
            show_think,
            final_stats,
            kwargs,
            current_ip,
            user_message,
            skill_id,
            history_log,
        ),
        content_type="text/event-stream",
    )
    # 使用公共的 SSE 响应头
    for key, value in create_sse_response_headers().items():
        response[key] = value
    response["X-Execution-ID"] = params["execution_id"]
    response["Access-Control-Expose-Headers"] = "X-Execution-ID"

    return response
