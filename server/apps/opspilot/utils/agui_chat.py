"""
AGUI协议聊天流式处理模块

实现AGUI(Agent UI)协议规范的流式聊天功能
"""

import json
import re
import time

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMModel, SkillRequestLog
from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.utils.agent_factory import create_agent_instance, create_sse_response_headers
from apps.opspilot.utils.stream_common import is_interrupt_requested_async
from apps.opspilot.utils.stream_common import process_think_content as _process_think_content
from apps.opspilot.utils.stream_common import split_think_content as _split_think_content

# 工具结果后的桥接型自述内容匹配模式，供提取与剥离两处复用（避免重复编译）。
_META_PREAMBLE_PATTERN = re.compile(
    r"^\s*(?:好的[，,\s]*|好[的吧]?[，,\s]*|OK[,\s]*|Okay[,\s]*)?"
    r"(?:我已经(?:成功)?获取(?:到|到了)|我已(?:经)?获取(?:到|到了)|现在我需要|接下来(?:我)?(?:需要|将)|"
    r"根据工具结果|根据返回结果|工具(?:已经)?返回了?|我现在可以|我将根据|"
    r"I have (?:retrieved|fetched)|Now I need to|Next I(?:'ll| will)|According to the tool result|The tool returned)"
    r"[^\n。！？!?]*(?:[。！？!?]|\n|$)\s*",
    re.IGNORECASE,
)


def _looks_like_implicit_thinking_prefix(content: str) -> bool:
    normalized = content.lstrip().lower()
    if not normalized:
        return True
    prefixes = ("thinking", "thinking process", "reasoning", "thought process", "思考", "思考过程")
    return any(prefix.startswith(normalized) or normalized.startswith(prefix) for prefix in prefixes)


def _sanitize_think_tag_residue(content: str, show_think: bool) -> str:
    """移除残余 think 标签，兜底处理孤立的 <think>/</think> 输出"""
    if not content:
        return content
    return content.replace("<think>", "").replace("</think>", "")


def _strip_post_tool_meta_preamble(content: str) -> str:
    """移除工具结果后的第一句桥接型自述内容"""
    if not content:
        return content

    stripped = _META_PREAMBLE_PATTERN.sub("", content, count=1)
    return stripped.lstrip()


def _extract_post_tool_meta_preamble(content: str) -> tuple[str, str]:
    """提取工具结果后的第一句桥接型自述内容，返回(前缀, 剩余正文)"""
    if not content:
        return "", content

    match = _META_PREAMBLE_PATTERN.match(content)
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


class AguiStreamState:
    """AGUI 流式状态机（F080）。

    将原先散落的 12 个可变状态字段（think 解析的 think_buffer / in_think_block /
    is_first_content / has_think_tags，以及 active_message_id / pending_content_events /
    buffer_pre_tool_content / post_tool_result_seen / emit_pending_as_thinking /
    pending_phase 等 pending/buffer/think-phase 标志）从一个匿名 12-key 字典升级为
    显式的状态机类。

    本类同时实现 ``__getitem__`` / ``__setitem__``，因此既能以属性方式访问，也兼容
    原有 ``state["key"]`` 的字典式读写——所有 THINKING vs TEXT_MESSAGE_CONTENT
    事件的顺序与分组、以及工具结果后的前言（preamble）处理逻辑完全不变，仅是把
    状态容器形式化，事件类型/字段保持不变。
    """

    # 显式声明全部状态字段，作为状态机契约（FSM 的“记忆”部分）。
    __slots__ = (
        "think_buffer",
        "in_think_block",
        "is_first_content",
        "has_think_tags",
        "active_message_id",
        "pending_content_events",
        "buffer_pre_tool_content",
        "post_tool_result_seen",
        "emit_pending_as_thinking",
        "pending_phase",
    )

    def __init__(self) -> None:
        # think 标签解析子状态
        self.think_buffer: str = ""
        self.in_think_block: bool = False
        self.is_first_content: bool = True
        self.has_think_tags: bool = True
        # 消息 / pending 缓冲 / think-phase 标志
        self.active_message_id = None
        self.pending_content_events: list = []
        self.buffer_pre_tool_content: bool = False
        self.post_tool_result_seen: bool = False
        self.emit_pending_as_thinking: bool = False
        self.pending_phase = None

    # 兼容原字典式访问（state["key"]），保证下游事件处理逻辑零改动。
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


def _init_agui_stream_state() -> "AguiStreamState":
    return AguiStreamState()


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


def _flush_pending_content_detecting_implicit_think(state: dict) -> list[str]:
    pending_content_events = state["pending_content_events"]
    if not pending_content_events:
        return []
    combined_content = "".join(event.get("delta", "") for event in pending_content_events)
    template_event = pending_content_events[-1]
    pending_content_events.clear()
    if "</think>" not in combined_content:
        return [_build_sse_line({**template_event, "delta": combined_content})]
    think_content, visible_content = combined_content.split("</think>", 1)
    lines = []
    think_content = _sanitize_think_tag_residue(think_content, True)
    visible_content = _sanitize_think_tag_residue(visible_content, True)
    if think_content.strip():
        lines.append(_build_sse_line(_build_thinking_event(think_content, template_event.get("timestamp"))))
    if visible_content:
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

    raw_output_content = output_content
    output_content = _sanitize_think_tag_residue(output_content, show_think)
    thinking_content = _sanitize_think_tag_residue(thinking_content, show_think)

    immediate_lines = []
    if show_think and enable_thinking_split and thinking_content:
        immediate_lines.append(_build_sse_line(_build_thinking_event(thinking_content, data_json.get("timestamp"))))

    if state["pending_phase"] == "pre_think_candidate" and data_json.get("message_id") == state["active_message_id"]:
        if raw_output_content == "</think>" and not state["pending_content_events"]:
            return "", immediate_lines
        if "</think>" in raw_output_content and _looks_like_implicit_thinking_prefix(raw_output_content):
            state["buffer_pre_tool_content"] = False
            state["pending_phase"] = None
            state["pending_content_events"].append({**data_json, "delta": raw_output_content})
            lines = _flush_pending_content_detecting_implicit_think(state)
            if not lines:
                return "", immediate_lines
            output_line = lines[-1]
            immediate_lines.extend(lines[:-1])
            return output_line, immediate_lines
        state["pending_content_events"].append({**data_json, "delta": raw_output_content})
        combined_content = "".join(event.get("delta", "") for event in state["pending_content_events"])
        if not _looks_like_implicit_thinking_prefix(combined_content):
            state["buffer_pre_tool_content"] = False
            state["pending_phase"] = None
            lines = _flush_pending_content_events(state)
            if not lines:
                return "", immediate_lines
            output_line = lines[-1]
            immediate_lines.extend(lines[:-1])
            return output_line, immediate_lines
        if "</think>" in combined_content:
            state["buffer_pre_tool_content"] = False
            state["pending_phase"] = None
            lines = _flush_pending_content_detecting_implicit_think(state)
            if not lines:
                return "", immediate_lines
            output_line = lines[-1]
            immediate_lines.extend(lines[:-1])
            return output_line, immediate_lines
        return "", immediate_lines

    if not output_content:
        return "", immediate_lines

    data_json["delta"] = output_content
    if state["buffer_pre_tool_content"] and data_json.get("message_id") == state["active_message_id"]:
        state["pending_content_events"].append(data_json.copy())
        return "", immediate_lines

    return _build_sse_line(data_json), immediate_lines


def _handle_tool_transition_event(event_type: str, data_json: dict, state: dict, show_think: bool, enable_thinking_split: bool) -> list[str]:
    if event_type == "TOOL_CALL_START":
        parent_message_id = data_json.get("parent_message_id")
        if state["buffer_pre_tool_content"] and parent_message_id == state["active_message_id"]:
            if state["emit_pending_as_thinking"]:
                lines = _flush_pending_content_as_thinking(state)
            else:
                # 将缓冲的文字内容作为正常 TEXT_MESSAGE_CONTENT 发送给前端
                lines = _flush_pending_content_events(state)
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

    if state["pending_phase"] == "pre_think_candidate" and data_json.get("message_id") == state["active_message_id"]:
        lines.extend(_flush_pending_content_detecting_implicit_think(state))

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
        state["pending_phase"] = (
            "post_tool" if state["post_tool_result_seen"] else ("pre_think_candidate" if show_think and enable_thinking_split else None)
        )
        if state["post_tool_result_seen"]:
            state["buffer_pre_tool_content"] = True
            state["emit_pending_as_thinking"] = show_think and enable_thinking_split
        else:
            state["buffer_pre_tool_content"] = bool(show_think and enable_thinking_split)
            state["emit_pending_as_thinking"] = False
        return _build_sse_line(data_json), []

    if event_type in {"THINKING_TEXT_MESSAGE_START", "THINKING_TEXT_MESSAGE_END"}:
        return "", []

    if event_type == "THINKING_TEXT_MESSAGE_CONTENT":
        # 只有在 show_think=True 时才输出 thinking 事件
        if show_think:
            return (
                _build_sse_line(_build_thinking_event(data_json.get("delta", ""), data_json.get("timestamp"))),
                [],
            )
        else:
            return "", []

    if event_type == "TEXT_MESSAGE_CONTENT":
        return _handle_text_message_content_event(data_json, state, show_think, enable_thinking_split)

    if event_type in {"TOOL_CALL_START", "TOOL_CALL_END", "TOOL_CALL_RESULT"}:
        return _build_sse_line(data_json), _handle_tool_transition_event(event_type, data_json, state, show_think, enable_thinking_split)

    if event_type == "TEXT_MESSAGE_END":
        return _build_sse_line(data_json), _handle_text_message_end_event(data_json, state, show_think, enable_thinking_split)

    return _build_sse_line(data_json), []


def _prepare_agui_chat_kwargs(params):
    """同步准备工作：取模型、格式化 chat_server 参数（F044）。

    抽成独立函数以便在生成器内经 sync_to_async 调用，让这些阻塞型 DB/格式化
    工作发生在首个 flush 之后，改善 TTFB。返回的内容/形状与此前完全一致。
    """
    llm_model = LLMModel.objects.get(id=params["llm_model"])
    chat_kwargs, doc_map, title_map = chat_service.format_chat_server_kwargs(params, llm_model)
    return chat_kwargs


async def _generate_agui_stream(params, skill_name, skill_type, show_think, final_stats, kwargs, current_ip, user_message, skill_id, history_log):
    try:
        logger.info(f"[AGUI Chat] 开始异步流处理 - skill_name: {skill_name}, skill_type: {skill_type}, show_think: {show_think}")
        # F044: 把取模型 / 格式化参数 / 创建 Agent 实例（构造 request/graph）的同步前置工作
        # 移入生成器内执行，经 sync_to_async 调用，避免在首个 flush 前阻塞请求线程，改善 TTFB。
        # 仍处于 try 内，任何异常仍以原有 ERROR 事件形状返回，线缆形状不变。
        chat_kwargs = await sync_to_async(_prepare_agui_chat_kwargs, thread_sensitive=True)(params)
        graph, request = await sync_to_async(create_agent_instance, thread_sensitive=True)(skill_type, chat_kwargs)
        accumulated_content = []
        state = _init_agui_stream_state()
        enable_thinking_split = _supports_thinking_events(request)
        execution_id = request.typed_extra_config().execution_id or request.thread_id

        async for sse_line in graph.agui_stream(request):
            if execution_id and await is_interrupt_requested_async(execution_id):
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
                except (json.JSONDecodeError, ValueError) as parse_err:
                    sample = sse_line[6:].strip()[:200]
                    logger.warning(f"[AGUI Chat] 跳过无法解析的 SSE 行: {parse_err}; 内容样本: {sample!r}")

            for line in immediate_lines:
                yield line

            if output_line:
                yield output_line

        final_stats["content"] = accumulated_content
        # 流已结束，同步落库（经 sync_to_async，与本生成器内其它 DB 调用一致）。此前用 daemon
        # 线程，进程退出/部署/缩容时 in-flight 写入被强杀 → 对话审计/技能日志丢失（与 sse_chat
        # 场景19 同类问题，AGUI 路径此前漏修）。await 确保写入在生成器结束前完成。
        if final_stats["content"]:
            await sync_to_async(_log_and_update_tokens_agui, thread_sensitive=True)(
                final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log
            )

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
    # 仅保留构造响应头所需的轻量同步处理（不含 DB / 格式化），其余阻塞型前置工作
    # 已下沉到生成器内（F044）。
    show_think = params.get("show_think", True)  # 使用 get 而不是 pop，保留值给 format_chat_server_kwargs
    skill_type = params.get("skill_type")
    params.pop("group", 0)
    params["execution_id"] = params.get("execution_id") or params.get("thread_id") or str(int(time.time() * 1000))

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": []}
    response = StreamingHttpResponse(
        _generate_agui_stream(
            params,
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
