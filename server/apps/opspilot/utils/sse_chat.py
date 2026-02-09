import json
import re
import threading
import time

from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMModel
from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.utils.agent_factory import create_agent_instance, create_sse_response_headers, normalize_llm_error_message
from apps.opspilot.utils.bot_utils import insert_skill_log


def generate_stream_error(message):
    """通用的流式错误生成函数"""

    async def generator():
        error_chunk = {
            "choices": [{"delta": {"content": message}, "index": 0, "finish_reason": "stop"}],
            "id": "error",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"

    # 直接使用异步生成器
    response = StreamingHttpResponse(generator(), content_type="text/event-stream")
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


def _generate_agent_stream(graph, request, skill_name, show_think):
    """生成 Agent 流式数据（异步生成器）"""
    accumulated_content = ""
    think_buffer = ""
    in_think_block = False
    is_first_content = True
    has_think_tags = True
    collected_custom_events = []

    async def run_stream():
        """异步运行流式处理"""
        nonlocal accumulated_content, think_buffer, in_think_block, is_first_content, has_think_tags

        try:
            # 使用 agui_stream 获取所有事件类型（包括 CUSTOM 事件）
            async for sse_line in graph.agui_stream(request):
                # 解析 SSE 事件
                if not sse_line.startswith("data: "):
                    continue
                try:
                    event_data = json.loads(sse_line[6:].strip())
                except (json.JSONDecodeError, ValueError):
                    continue

                event_type = event_data.get("type", "")

                # 收集 CUSTOM 事件（如 browser_step_progress）
                if event_type == "CUSTOM":
                    collected_custom_events.append(event_data)
                    continue

                # 只处理 TEXT_MESSAGE_CONTENT 事件
                if event_type != "TEXT_MESSAGE_CONTENT":
                    continue

                content_chunk = event_data.get("delta", "")
                if content_chunk:
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

                    if output_content:
                        stream_chunk = _create_stream_chunk(output_content, skill_name)
                        yield f"data: {json.dumps(stream_chunk)}\n\n"

            # 处理剩余缓冲区内容
            if not show_think and not in_think_block and think_buffer:
                stream_chunk = _create_stream_chunk(think_buffer, skill_name)
                yield f"data: {json.dumps(stream_chunk)}\n\n"

            # 发送完成标志
            final_chunk = _create_stream_chunk("", skill_name, "stop")
            yield f"data: {json.dumps(final_chunk)}\n\n"

            # 输出收集的 CUSTOM 事件（供 engine.py 的 _extract_browser_steps 使用）
            for custom_event in collected_custom_events:
                yield f"data: {json.dumps(custom_event)}\n\n"

            # 返回统计信息
            yield ("STATS", accumulated_content)

        except Exception as e:
            logger.error(f"Agent stream error: {e}", exc_info=True)

            # 使用公共方法提取友好的错误信息
            error_msg = normalize_llm_error_message(str(e))

            error_chunk = _create_error_chunk(error_msg, skill_name)
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield ("STATS", "")

    # 直接返回异步生成器
    return run_stream()


def _log_and_update_tokens_sync(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log=None):
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
        if history_log:
            history_log.conversation = final_content
            history_log.save()
        if current_ip:
            insert_skill_log(current_ip, skill_id, log_data, kwargs, user_message=user_message)

    except Exception as e:
        logger.error(f"Log update error: {e}")


def stream_chat(params, skill_name, kwargs, current_ip, user_message, skill_id=None, history_log=None):
    """流式聊天接口 - 返回 StreamingHttpResponse"""
    # 直接使用异步生成器，不需要额外包装
    response = StreamingHttpResponse(
        create_stream_generator(params, skill_name, kwargs, current_ip, user_message, skill_id, history_log), content_type="text/event-stream"
    )

    # 使用公共的 SSE 响应头
    for key, value in create_sse_response_headers().items():
        response[key] = value

    return response


def create_stream_generator(params, skill_name, kwargs, current_ip, user_message, skill_id=None, history_log=None):
    """创建流式生成器 - 返回异步生成器供内部或外部使用"""
    llm_model = LLMModel.objects.get(id=params["llm_model"])
    show_think = params.pop("show_think", True)
    skill_type = params.get("skill_type")
    params.pop("group", 0)

    chat_kwargs, doc_map, title_map = chat_service.format_chat_server_kwargs(params, llm_model)

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": ""}

    async def generate_stream():
        try:
            # 创建对应的 Agent 实例和请求对象
            graph, request = create_agent_instance(skill_type, chat_kwargs)

            # 使用直接调用 agent 方法生成流
            stream_gen = _generate_agent_stream(graph, request, skill_name, show_think)

            async for chunk in stream_gen:
                if isinstance(chunk, tuple) and chunk[0] == "STATS":
                    # 收集统计信息
                    _, final_stats["content"] = chunk

                    # 在流结束时同步处理日志记录
                    if final_stats["content"]:
                        # 使用线程异步处理日志记录，避免阻塞流式响应
                        def log_in_background():
                            _log_and_update_tokens_sync(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log)

                        threading.Thread(target=log_in_background, daemon=True).start()
                else:
                    # 发送流式数据
                    yield chunk

        except Exception as e:
            logger.error(f"Stream chat error: {e}", exc_info=True)
            error_chunk = _create_error_chunk(f"聊天错误: {str(e)}", skill_name)
            yield f"data: {json.dumps(error_chunk)}\n\n"

    return generate_stream()
