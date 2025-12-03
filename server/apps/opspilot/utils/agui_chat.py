"""
AGUI协议聊天流式处理模块

实现AGUI(Agent UI)协议规范的流式聊天功能
"""

import json
import logging
import threading
import time

from django.http import StreamingHttpResponse

from apps.core.utils.async_utils import create_async_compatible_generator
from apps.opspilot.models import LLMModel, SkillRequestLog
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.utils.agent_factory import (
    create_agent_instance,
    create_sse_response_headers,
    normalize_llm_error_message,
    run_async_generator_in_loop,
)

logger = logging.getLogger(__name__)


def _generate_agui_stream(graph, request, skill_name, show_think=True):
    """
    生成AGUI协议的流式数据（使用 asyncio 运行异步方法）

    直接调用 graph.agui_stream() 方法，该方法已经返回符合 AGUI 协议的 SSE 格式字符串
    """
    accumulated_content = ""

    async def run_stream():
        """异步运行流式处理"""
        nonlocal accumulated_content

        try:
            # 调用 graph 的 agui_stream 方法，返回已格式化的 SSE 字符串
            async for sse_line in graph.agui_stream(request):
                # sse_line 已经是 "data: {...}\n\n" 格式

                # 尝试提取内容用于日志记录
                if sse_line.startswith("data: "):
                    try:
                        data_str = sse_line[6:].strip()
                        data_json = json.loads(data_str)

                        # 累积文本内容用于日志
                        if data_json.get("type") == "TEXT_MESSAGE_CONTENT":
                            delta = data_json.get("delta", "")
                            accumulated_content += delta
                    except (json.JSONDecodeError, ValueError):
                        pass

                # 直接转发 SSE 行
                yield sse_line

            # 返回统计信息
            yield ("STATS", accumulated_content)

        except Exception as e:
            logger.error(f"AGUI Agent stream error: {e}", exc_info=True)

            # 使用公共方法提取友好的错误信息
            error_msg = normalize_llm_error_message(str(e))

            error_data = {"type": "RUN_ERROR", "message": error_msg, "code": "EXECUTION_ERROR", "timestamp": int(time.time() * 1000)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
            yield ("STATS", "")

    # 使用公共的异步事件循环运行器
    yield from run_async_generator_in_loop(run_stream)


def _create_agui_error_chunk(error_message, skill_name):
    """创建AGUI格式的错误消息"""
    return {"event": "error", "data": {"error": error_message, "skill": skill_name}}


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

    chat_kwargs, doc_map, title_map = llm_service.format_chat_server_kwargs(params, llm_model)

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": ""}

    def generate_stream():
        try:
            # 创建 agent 实例
            graph, request = create_agent_instance(skill_type, chat_kwargs)

            # 生成流式数据
            stream_gen = _generate_agui_stream(graph, request, skill_name, show_think)

            for chunk in stream_gen:
                if isinstance(chunk, tuple) and chunk[0] == "STATS":
                    # 收集统计信息
                    _, final_stats["content"] = chunk

                    # 在流结束时异步处理日志记录
                    if final_stats["content"]:

                        def log_in_background():
                            _log_and_update_tokens_agui(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log)

                        threading.Thread(target=log_in_background, daemon=True).start()
                else:
                    # 发送流式数据
                    yield chunk

        except Exception as e:
            logger.error(f"AGUI stream chat error: {e}", exc_info=True)
            error_data = {"type": "ERROR", "error": f"聊天错误: {str(e)}", "timestamp": int(time.time() * 1000)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    # 使用异步兼容的生成器来解决 ASGI 环境下的问题
    async_generator = create_async_compatible_generator(generate_stream())

    response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
    # 使用公共的 SSE 响应头
    for key, value in create_sse_response_headers().items():
        response[key] = value

    return response
