"""
流式聊天共享内部逻辑（F056）。
"""

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, Optional

from django.http import StreamingHttpResponse

from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

__all__ = [
    "process_think_buffer",
    "process_think_content",
    "split_think_content",
    "is_interrupt_requested_async",
    "make_sse_response",
    "make_sse_error_response",
    "apply_sse_response_headers",
]


def apply_sse_response_headers(response: StreamingHttpResponse, extra_headers: Optional[dict[str, str]] = None) -> StreamingHttpResponse:
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Cache-Control"
    if extra_headers:
        for key, value in extra_headers.items():
            response[key] = value
    return response


def make_sse_response(stream: Callable[[], AsyncIterator | Iterator], *, extra_headers: Optional[dict[str, str]] = None) -> StreamingHttpResponse:
    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    return apply_sse_response_headers(response, extra_headers)


def make_sse_error_response(error_message: str) -> StreamingHttpResponse:
    async def error_generator():
        error_data = {"result": False, "message": error_message, "error": True}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return make_sse_response(error_generator)


def process_think_buffer(think_buffer, in_think_block):
    """处理思考缓冲区，返回可输出的内容。

    （原 sse_chat._process_think_buffer，逻辑保持不变）
    """
    output_chunks = []

    while think_buffer:
        if not in_think_block:
            think_start_pos = think_buffer.find("<think>")
            if think_start_pos != -1:
                # 输出思考标签前的内容
                if think_start_pos > 0:
                    output_chunks.append(think_buffer[:think_start_pos])
                in_think_block = True
                think_buffer = think_buffer[think_start_pos + 7 :]
            else:
                # 保留最后8个字符防止标签分割
                if len(think_buffer) > 8:
                    output_chunks.append(think_buffer[:-8])
                    think_buffer = think_buffer[-8:]
                break
        else:
            think_end_pos = think_buffer.find("</think>")
            if think_end_pos != -1:
                in_think_block = False
                think_buffer = think_buffer[think_end_pos + 8 :]
            else:
                think_buffer = ""
                break

    return "".join(output_chunks), think_buffer, in_think_block


def process_think_content(
    content_chunk,
    think_buffer,
    in_think_block,
    is_first_content,
    show_think,
    has_think_tags,
):
    """处理思考过程相关的内容过滤。

    （原 sse_chat._process_think_content，逻辑保持不变）
    """
    if show_think:
        return content_chunk, think_buffer, in_think_block, False, has_think_tags

    # 首次内容检查是否包含think标签
    if is_first_content:
        think_buffer += content_chunk
        if "<think>" not in think_buffer:
            return think_buffer, "", in_think_block, False, False
        else:
            has_think_tags = True
            # 首包已整体进入缓冲区，后续通用逻辑不得再次追加同一 chunk。
            content_chunk = ""
            if think_buffer.lstrip().startswith("<think>"):
                in_think_block = True
                think_start = think_buffer.find("<think>")
                think_buffer = think_buffer[think_start + 7 :]

    if not has_think_tags:
        return content_chunk, think_buffer, in_think_block, False, has_think_tags

    # 处理思考内容
    think_buffer += content_chunk
    output_content, think_buffer, in_think_block = process_think_buffer(think_buffer, in_think_block)

    return output_content, think_buffer, in_think_block, False, has_think_tags


def split_think_content(
    content_chunk,
    think_buffer,
    in_think_block,
    is_first_content,
    has_think_tags,
):
    """将内容拆分为可见内容和 think 内容，复用 show_think=False 的识别逻辑。

    （原 sse_chat._split_think_content，逻辑保持不变）
    """
    visible_content = ""
    thinking_content = ""

    if is_first_content:
        think_buffer += content_chunk
        if "<think>" not in think_buffer:
            return think_buffer, "", "", in_think_block, False, False

        has_think_tags = True
        think_start = think_buffer.find("<think>")
        visible_content += think_buffer[:think_start]
        think_buffer = think_buffer[think_start + 7 :]
        # 首包已整体进入缓冲区，避免在下方重复追加造成正文重复。
        content_chunk = ""
        in_think_block = True
        is_first_content = False

    if not has_think_tags:
        return content_chunk, "", think_buffer, in_think_block, False, has_think_tags

    think_buffer += content_chunk

    while think_buffer:
        if in_think_block:
            think_end = think_buffer.find("</think>")
            if think_end == -1:
                thinking_content += think_buffer
                think_buffer = ""
                break

            thinking_content += think_buffer[:think_end]
            think_buffer = think_buffer[think_end + 8 :]
            in_think_block = False
            continue

        think_start = think_buffer.find("<think>")
        if think_start == -1:
            visible_content += think_buffer
            think_buffer = ""
            break

        visible_content += think_buffer[:think_start]
        think_buffer = think_buffer[think_start + 7 :]
        in_think_block = True

    return visible_content, thinking_content, think_buffer, in_think_block, False, has_think_tags
