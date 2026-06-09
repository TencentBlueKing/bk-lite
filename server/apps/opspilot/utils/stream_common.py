"""
流式聊天共享内部逻辑（F056）。

两套流式协议——OpenAI chunk 风格（sse_chat.stream_chat）与 AGUI 事件风格
（agui_chat）——此前各自重复实现 think 标签解析、中断检查、token 记账等逻辑。

本模块仅抽取这些“内部共享逻辑”，不涉及任何线缆帧编码：

- OpenAI chunk 仍由 sse_chat 自己的 ``_create_stream_chunk`` / ``_create_error_chunk`` 编码；
- AGUI 事件仍由 agui_chat 自己的 ``_build_sse_line`` / ``_build_thinking_event`` 编码。

两种协议发往前端的字节序列保持与重构前完全一致；各自的错误事件形状
（AGUI 的 ERROR/RUN_ERROR、OpenAI 的 error chunk）也不在此处改动。
"""

from apps.opspilot.utils.execution_interrupt import is_interrupt_requested_async

__all__ = [
    "process_think_buffer",
    "process_think_content",
    "split_think_content",
    "is_interrupt_requested_async",
]


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
            if think_buffer.lstrip().startswith("<think>"):
                in_think_block = True
                think_start = think_buffer.find("<think>")
                think_buffer = think_buffer[think_start + 7 :]
                return "", think_buffer, in_think_block, False, has_think_tags

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
