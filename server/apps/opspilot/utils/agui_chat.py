"""
AGUI协议聊天流式处理模块

实现AGUI(Agent UI)协议规范的流式聊天功能
"""
import json
import logging
import threading
import time

import requests
from django.conf import settings
from django.http import StreamingHttpResponse

from apps.core.utils.async_utils import create_async_compatible_generator
from apps.opspilot.models import LLMModel, SkillRequestLog, SkillTypeChoices
from apps.opspilot.services.llm_service import llm_service
from apps.opspilot.utils.chat_server_helper import ChatServerHelper

logger = logging.getLogger(__name__)


def _generate_agui_stream(url, headers, chat_kwargs, skill_name, show_think=True):
    """
    生成AGUI协议的流式数据

    直接转发后端返回的AGUI格式数据，格式：
    data: {"type":"RUN_STARTED",...}
    data: {"type":"TEXT_MESSAGE_START",...}
    data: {"type":"TEXT_MESSAGE_CONTENT",...}
    data: {"type":"TEXT_MESSAGE_END",...}
    data: {"type":"RUN_FINISHED",...}
    """
    try:
        logger.info(f"AGUI request to {url}, headers: {headers}, kwargs: {chat_kwargs}")
        response = requests.post(url, json=chat_kwargs, headers=headers, timeout=300.0, stream=True)
        response.raise_for_status()
        logger.info(f"AGUI response status: {response.status_code}, headers: {dict(response.headers)}")

        # 用于累积完整回复内容（用于日志记录）
        full_response = ""
        total_tokens = 0

        # 逐行读取并转发
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            logger.info(f"AGUI line received: {line}")

            # 检查是否是 data: 开头的行
            if line.startswith("data:"):
                data_str = line[5:].strip()

                try:
                    data_json = json.loads(data_str)
                    event_type = data_json.get("type")

                    logger.info(f"AGUI event type: {event_type}, data: {data_json}")

                    # 累积文本内容用于日志
                    if event_type == "TEXT_MESSAGE_CONTENT":
                        delta = data_json.get("delta", "")
                        full_response += delta

                    # 记录token信息
                    if event_type == "RUN_FINISHED":
                        # 如果有token统计信息，记录下来
                        if "usage" in data_json:
                            total_tokens = data_json["usage"].get("total_tokens", 0)

                    # 直接转发原始数据行
                    yield f"{line}\n"

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse AGUI data: {data_str}, error: {e}")
                    # 即使解析失败也转发原始数据
                    yield f"{line}\n"
            else:
                # 其他行（如空行）也转发
                yield f"{line}\n"

        # 流结束，返回统计信息用于日志记录
        if full_response or total_tokens:
            stats = {"response": full_response, "total_tokens": total_tokens, "completion_tokens": 0, "prompt_tokens": 0}  # AGUI协议可能不区分，如果有再补充
            yield ("STATS", json.dumps(stats, ensure_ascii=False))

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error in AGUI stream: {e}")
        error_data = {
            "type": "ERROR",
            "error": f"HTTP错误: {e.response.status_code if e.response else 'Unknown'}",
            "timestamp": int(time.time() * 1000),
        }
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n"
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in AGUI stream: {e}")
        error_data = {"type": "ERROR", "error": f"请求错误: {str(e)}", "timestamp": int(time.time() * 1000)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n"
    except Exception as e:
        logger.error(f"Error in AGUI stream: {e}")
        error_data = {"type": "ERROR", "error": str(e), "timestamp": int(time.time() * 1000)}
        yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n"


def _create_agui_error_chunk(error_message, skill_name):
    """创建AGUI格式的错误消息"""
    return {"event": "error", "data": {"error": error_message, "skill": skill_name}}


def _log_and_update_tokens_agui(final_stats, skill_name, skill_id, current_ip, kwargs, user_message, show_think, history_log=None):
    """
    记录AGUI协议的请求日志并更新token统计
    """
    try:
        if not final_stats.get("content"):
            return

        stats_data = json.loads(final_stats["content"])

        # 创建或更新日志
        if history_log:
            history_log.completion_tokens = stats_data.get("completion_tokens", 0)
            history_log.prompt_tokens = stats_data.get("prompt_tokens", 0)
            history_log.total_tokens = stats_data.get("total_tokens", 0)
            history_log.response = stats_data.get("response", "")
            history_log.save()
        else:
            # skill_id必须存在才能创建日志
            if not skill_id:
                logger.warning(f"AGUI log skipped: skill_id is None for skill_name={skill_name}")
                return

            # 构建response_detail，包含token统计和响应内容
            response_detail = {
                "completion_tokens": stats_data.get("completion_tokens", 0),
                "prompt_tokens": stats_data.get("prompt_tokens", 0),
                "total_tokens": stats_data.get("total_tokens", 0),
                "response": stats_data.get("response", ""),
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
    params.pop("group", 0)

    chat_kwargs, doc_map, title_map = llm_service.format_chat_server_kwargs(params, llm_model)

    # 使用AGUI协议的接口
    url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_chatbot_workflow_agui"

    # # 根据技能类型选择不同的AGUI接口（如果有的话）
    if params.get("skill_type") == SkillTypeChoices.BASIC_TOOL:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_react_agent_agui"
    elif params.get("skill_type") == SkillTypeChoices.PLAN_EXECUTE:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_plan_and_execute_agent_agui"
    elif params.get("skill_type") == SkillTypeChoices.LATS:
        url = f"{settings.METIS_SERVER_URL}/api/agent/invoke_lats_agent_agui"

    # 用于存储最终统计信息的共享变量
    final_stats = {"content": ""}

    def generate_stream():
        try:
            headers = ChatServerHelper.get_chat_server_header()
            stream_gen = _generate_agui_stream(url, headers, chat_kwargs, skill_name, show_think)

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
            logger.error(f"AGUI stream chat error: {e}")
            error_data = {"type": "ERROR", "error": f"聊天错误: {str(e)}", "timestamp": int(time.time() * 1000)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n"

    # 使用异步兼容的生成器来解决 ASGI 环境下的问题
    async_generator = create_async_compatible_generator(generate_stream())

    response = StreamingHttpResponse(async_generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["X-Accel-Buffering"] = "no"  # Nginx
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "Cache-Control"

    return response
