import json
import re
import time

from asgiref.sync import sync_to_async
from django.http import StreamingHttpResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import LLMModel
from apps.opspilot.services.chat_service import chat_service
from apps.opspilot.utils.agent_factory import create_agent_instance, create_sse_response_headers, normalize_llm_error_message
from apps.opspilot.utils.bot_utils import insert_skill_log
from apps.opspilot.utils import stream_common


def create_error_stream_response(error_message):
    """
    创建错误的流式响应，用于在流式模式下返回错误信息。

    放在此处而非 LLMViewSet 上，避免仅为使用该静态辅助方法就被迫导入整个
    LLMViewSet（及其大量依赖）。LLMViewSet 仍保留同名静态方法委托到此函数。
    """

    async def error_generator():
        error_data = {"result": False, "message": error_message, "error": True}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(error_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"  # Nginx
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Cache-Control"
    return response


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


# --- think 标签解析共享逻辑（F056）---
# 实现已抽取至 apps.opspilot.utils.stream_common，供本模块（OpenAI chunk 协议）
# 与 agui_chat（AGUI 协议）共用。此处保留原私有名作为薄别名，以兼容历史导入
# （agui_chat 仍从本模块导入 _process_think_content / _split_think_content）。
_process_think_buffer = stream_common.process_think_buffer
_process_think_content = stream_common.process_think_content
_split_think_content = stream_common.split_think_content


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
    """
    同步记录日志和更新 token 统计。

    此函数在流结束后调用，不会阻塞流式响应。
    失败时记录错误日志但不抛出异常，确保不影响已发送的响应。
    """
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
        # 记录详细错误信息，包含上下文便于排查
        logger.error(
            "SSE persistence failed: skill_name=%s, skill_id=%s, error=%s",
            skill_name,
            skill_id,
            str(e),
            exc_info=True,
        )


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


def _prepare_stream_prerequisites(params):
    """同步准备工作：取模型、格式化 chat_server 参数（F044）。

    抽成独立函数以便在生成器内经 sync_to_async 调用，让这些阻塞型 DB/格式化
    工作发生在首个 flush 之后，改善 TTFB。返回的内容/形状与此前完全一致。
    """
    llm_model = LLMModel.objects.get(id=params["llm_model"])
    skill_type = params.get("skill_type")
    params.pop("group", 0)
    chat_kwargs, doc_map, title_map = chat_service.format_chat_server_kwargs(params, llm_model)
    return skill_type, chat_kwargs


def create_stream_generator(params, skill_name, kwargs, current_ip, user_message, skill_id=None, history_log=None):
    """创建流式生成器 - 返回异步生成器供内部或外部使用"""
    show_think = params.get("show_think", True)  # 使用 get 而不是 pop，保留值给 format_chat_server_kwargs

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": ""}

    async def generate_stream():
        try:
            # F044: 将同步前置工作（取模型 / 格式化参数 / 创建 Agent 实例）移入生成器内，
            # 经 sync_to_async 执行，避免在首个 flush 前阻塞请求线程，改善 TTFB。
            skill_type, chat_kwargs = await sync_to_async(_prepare_stream_prerequisites, thread_sensitive=True)(params)

            # 创建对应的 Agent 实例和请求对象
            graph, request = await sync_to_async(create_agent_instance, thread_sensitive=True)(skill_type, chat_kwargs)

            # 使用直接调用 agent 方法生成流
            stream_gen = _generate_agent_stream(graph, request, skill_name, show_think)

            async for chunk in stream_gen:
                if isinstance(chunk, tuple) and chunk[0] == "STATS":
                    # 收集统计信息
                    _, final_stats["content"] = chunk

                    # 流已结束，同步执行持久化（不会阻塞流式响应）
                    # 注意：STATS 事件是流的最后一个事件，此时客户端已收到所有数据
                    if final_stats["content"]:
                        _log_and_update_tokens_sync(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log)
                else:
                    # 发送流式数据
                    yield chunk

        except Exception as e:
            logger.error(f"Stream chat error: {e}", exc_info=True)
            error_chunk = _create_error_chunk(f"聊天错误: {str(e)}", skill_name)
            yield f"data: {json.dumps(error_chunk)}\n\n"

    return generate_stream()
