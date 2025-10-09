import json
import os
import re
import threading
import time

import requests
from django.conf import settings
from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.utils.async_utils import create_async_compatible_generator
from apps.opspilot.enum import SkillTypeChoices
from apps.opspilot.models import LLMModel
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.utils.bot_utils import insert_skill_log
from apps.opspilot.utils.chat_server_helper import ChatServerHelper


def generate_stream_error(message):
    """通用的流式错误生成函数"""

    def generator():
        error_chunk = {
            "choices": [{"delta": {"content": message}, "index": 0, "finish_reason": "stop"}],
            "id": "error",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"

    # 使用异步兼容的生成器来解决 ASGI 环境下的问题
    async_generator = create_async_compatible_generator(generator())
    response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
    # 添加必要的头信息以防止缓冲
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _process_think_buffer(think_buffer, in_think_block):
    """处理思考缓冲区，返回可输出的内容"""
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


def _process_think_content(
    content_chunk,
    think_buffer,
    in_think_block,
    is_first_content,
    show_think,
    has_think_tags,
):
    """处理思考过程相关的内容过滤"""
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
    output_content, think_buffer, in_think_block = _process_think_buffer(think_buffer, in_think_block)

    return output_content, think_buffer, in_think_block, False, has_think_tags


def _create_stream_chunk(content, skill_name, finish_reason=None):
    """创建流式响应块"""
    return {
        "choices": [{"delta": {"content": content}, "index": 0, "finish_reason": finish_reason}],
        "id": skill_name,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
    }


def _create_error_chunk(error_message, skill_name):
    """创建错误响应块"""
    return {
        "choices": [{"delta": {"content": error_message}, "index": 0, "finish_reason": "stop"}],
        "id": skill_name,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
    }


def _process_sse_line(
    line,
    accumulated_content,
    think_buffer,
    in_think_block,
    is_first_content,
    show_think,
    has_think_tags,
):
    """处理单行SSE数据"""
    if not line or not line.strip() or not line.startswith("data: "):
        return (
            accumulated_content,
            think_buffer,
            in_think_block,
            is_first_content,
            None,
            has_think_tags,
        )

    data_str = line[6:]  # 移除 "data: " 前缀

    # 检查是否为结束标志
    if data_str.strip() == "[DONE]":
        return (
            accumulated_content,
            think_buffer,
            in_think_block,
            is_first_content,
            "DONE",
            has_think_tags,
        )

    try:
        data = json.loads(data_str)
        output_content = ""

        # 检查是否有choices数组并且不为空
        if "choices" in data and data["choices"]:
            choice = data["choices"][0]

            # 检查是否结束
            if choice.get("finish_reason") == "stop":
                return (
                    accumulated_content,
                    think_buffer,
                    in_think_block,
                    is_first_content,
                    "DONE",
                    has_think_tags,
                )

            # 处理内容增量
            if "delta" in choice and "content" in choice["delta"]:
                content_chunk = choice["delta"]["content"]
                if content_chunk:  # 只有非空内容才处理
                    accumulated_content += content_chunk

                    (
                        output_content,
                        think_buffer,
                        in_think_block,
                        is_first_content,
                        has_think_tags,
                    ) = _process_think_content(
                        content_chunk,
                        think_buffer,
                        in_think_block,
                        is_first_content,
                        show_think,
                        has_think_tags,
                    )

        return (
            accumulated_content,
            think_buffer,
            in_think_block,
            is_first_content,
            output_content,
            has_think_tags,
        )

    except json.JSONDecodeError:
        # 忽略无效的JSON数据
        return (
            accumulated_content,
            think_buffer,
            in_think_block,
            is_first_content,
            None,
            has_think_tags,
        )


def _generate_sse_stream(url, headers, chat_kwargs, skill_name, show_think):
    """生成SSE流式数据"""
    accumulated_content = ""
    think_buffer = ""
    in_think_block = False
    is_first_content = True
    has_think_tags = True
    sse_headers = {
        **headers,
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }

    # SSL验证配置 - 从环境变量读取
    ssl_verify = os.getenv("METIS_SSL_VERIFY", "false").lower() == "true"

    try:
        res = requests.post(
            url,
            headers=sse_headers,
            json=chat_kwargs,
            timeout=300,
            verify=ssl_verify,
            stream=True,
        )
        res.raise_for_status()

        for line in res.iter_lines(decode_unicode=True):
            result = _process_sse_line(
                line,
                accumulated_content,
                think_buffer,
                in_think_block,
                is_first_content,
                show_think,
                has_think_tags,
            )
            (
                accumulated_content,
                think_buffer,
                in_think_block,
                is_first_content,
                output,
                has_think_tags,
            ) = result

            if output == "DONE":
                break
            elif output:
                stream_chunk = _create_stream_chunk(output, skill_name)
                yield f"data: {json.dumps(stream_chunk)}\n\n"

        # 处理剩余缓冲区内容
        if not show_think and not in_think_block and think_buffer:
            stream_chunk = _create_stream_chunk(think_buffer, skill_name)
            yield f"data: {json.dumps(stream_chunk)}\n\n"

        # 发送完成标志
        final_chunk = _create_stream_chunk("", skill_name, "stop")
        yield f"data: {json.dumps(final_chunk)}\n\n"

        # 使用特殊标识返回统计信息
        yield ("STATS", accumulated_content)

    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        error_chunk = _create_error_chunk(f"流式处理错误: {str(e)}", skill_name)
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield ("STATS", "")


def _log_and_update_tokens_sync(
    final_stats,
    skill_name,
    skill_id,
    current_ip,
    kwargs,
    user_message,
    show_think,
):
    try:
        # 处理最终内容
        final_content = final_stats["content"]
        if not show_think:
            final_content = re.sub(r"<think>.*?</think>", "", final_content, flags=re.DOTALL).strip()

        # 记录日志
        log_data = {
            "id": skill_name,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": skill_name,
            "choices": [
                {
                    "message": {"role": "assistant", "content": final_content},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ],
        }

        insert_skill_log(current_ip, skill_id, log_data, kwargs, user_message=user_message)

    except Exception as e:
        logger.error(f"Log update error: {e}")


def stream_chat(params, skill_name, kwargs, current_ip, user_message, skill_id=None):
    llm_model = LLMModel.objects.get(id=params["llm_model"])
    show_think = params.pop("show_think", True)
    params.pop("group", 0)

    chat_kwargs, doc_map, title_map = llm_service.format_chat_server_kwargs(params, llm_model)

    url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_chatbot_workflow_sse"
    if params.get("skill_type") == SkillTypeChoices.BASIC_TOOL:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_react_agent_sse"
    elif params.get("skill_type") == SkillTypeChoices.PLAN_EXECUTE:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_plan_and_execute_agent_sse"
    elif params.get("skill_type") == SkillTypeChoices.LATS:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_lats_agent_sse"

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": ""}

    def generate_stream():
        try:
            headers = ChatServerHelper.get_chat_server_header()
            stream_gen = _generate_sse_stream(url, headers, chat_kwargs, skill_name, show_think)

            for chunk in stream_gen:
                if isinstance(chunk, tuple) and chunk[0] == "STATS":
                    # 收集统计信息
                    (
                        _,
                        final_stats["content"],
                    ) = chunk

                    # 在流结束时同步处理日志记录
                    if final_stats["content"]:
                        # 使用线程异步处理日志记录，避免阻塞流式响应
                        def log_in_background():
                            _log_and_update_tokens_sync(
                                final_stats,
                                skill_name,
                                skill_id,
                                current_ip,
                                kwargs,
                                user_message,
                                show_think,
                            )

                        threading.Thread(target=log_in_background, daemon=True).start()
                else:
                    # 发送流式数据
                    yield chunk

        except Exception as e:
            logger.error(f"Stream chat error: {e}")
            error_chunk = _create_error_chunk(f"聊天错误: {str(e)}", skill_name)
            yield f"data: {json.dumps(error_chunk)}\n\n"

    # 使用异步兼容的生成器来解决 ASGI 环境下的问题
    async_generator = create_async_compatible_generator(generate_stream())
    response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"  # Nginx
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Cache-Control"

    return response
