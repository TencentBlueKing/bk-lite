"""
Agent 工厂模块

提供统一的 Agent 实例创建方法和通用工具函数，供 SSE 和 AGUI 协议共享使用
"""

import asyncio
import datetime
import time

from asgiref.sync import sync_to_async

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.agent.chatbot_workflow import ChatBotWorkflowGraph, ChatBotWorkflowRequest
from apps.opspilot.metis.llm.agent.lats_agent import LatsAgentGraph, LatsAgentRequest
from apps.opspilot.metis.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentGraph, PlanAndExecuteAgentRequest
from apps.opspilot.metis.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from apps.opspilot.models import SkillTypeChoices


def create_agent_instance(skill_type, chat_kwargs):
    """
    根据技能类型创建对应的 Agent 实例和请求对象

    Args:
        skill_type: 技能类型，来自 SkillTypeChoices
        chat_kwargs: Agent 请求参数字典

    Returns:
        tuple: (graph, request) - Agent 图实例和请求对象
    """
    if skill_type == SkillTypeChoices.BASIC_TOOL:
        request = ReActAgentRequest(**chat_kwargs)
        graph = ReActAgentGraph()
    elif skill_type == SkillTypeChoices.PLAN_EXECUTE:
        request = PlanAndExecuteAgentRequest(**chat_kwargs)
        graph = PlanAndExecuteAgentGraph()
    elif skill_type == SkillTypeChoices.LATS:
        request = LatsAgentRequest(**chat_kwargs)
        graph = LatsAgentGraph()
    else:
        # 默认使用 ChatBot Workflow
        request = ChatBotWorkflowRequest(**chat_kwargs)
        graph = ChatBotWorkflowGraph()

    return graph, request


def normalize_llm_error_message(error_msg: str) -> str:
    """
    标准化 LLM 错误信息，返回用户友好的错误描述

    Args:
        error_msg: 原始错误信息字符串

    Returns:
        str: 友好的错误信息
    """
    if "Error code: 502" in error_msg:
        return "LLM服务暂时不可用(502)，请检查模型配置或稍后重试"
    elif "Error code: 503" in error_msg:
        return "LLM服务过载(503)，请稍后重试"
    elif "Error code: 504" in error_msg:
        return "LLM服务响应超时(504)，请稍后重试"
    elif "Error code: 401" in error_msg:
        return "LLM API密钥无效(401)，请检查模型配置"
    elif "Error code: 429" in error_msg:
        return "LLM请求频率超限(429)，请稍后重试"
    elif "Connection" in error_msg or "timeout" in error_msg.lower():
        return f"LLM服务连接失败: {error_msg}"
    else:
        return f"流式处理错误: {error_msg}"


def run_async_generator_in_loop(async_gen_func):
    """
    在新的事件循环中运行异步生成器

    Args:
        async_gen_func: 异步生成器函数

    Yields:
        异步生成器产生的结果
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async_gen = async_gen_func()
        while True:
            try:
                result = loop.run_until_complete(async_gen.__anext__())
                yield result
                # 添加延迟,确保有足够时间让服务器发送数据
                # 增加到20ms,确保网络栈有足够时间刷新
                time.sleep(0.02)  # 20毫秒延迟
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def create_async_wrapper_for_sync_generator(sync_generator):
    """
    将同步生成器包装为异步生成器,供 Django ASGI StreamingHttpResponse 使用
    使用 sync_to_async 在线程中执行同步操作,避免数据库访问冲突

    Args:
        sync_generator: 同步生成器对象

    Yields:
        生成器产生的每个 chunk
    """

    def get_next_chunk():
        """同步函数:获取下一个chunk"""
        try:
            return next(sync_generator)
        except StopIteration:
            return None

    # 将同步函数转为异步
    async_get_next = sync_to_async(get_next_chunk, thread_sensitive=False)

    chunk_index = 0
    while True:
        chunk = await async_get_next()
        if chunk is None:
            break
        chunk_index += 1

        # 如果不是第一个chunk,在发送前等待,让前一个chunk有时间被刷新
        if chunk_index > 1:
            await asyncio.sleep(0.01)  # 10毫秒延迟

        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        logger.debug(f"[AsyncWrapper] 发送 chunk #{chunk_index} at {now}")
        yield chunk


def create_sse_response_headers():
    """
    创建 SSE 流式响应的标准响应头

    Returns:
        dict: 响应头字典
    """
    return {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",  # Nginx 禁用缓冲
        "Pragma": "no-cache",  # HTTP/1.0 兼容
        "Expires": "0",  # 立即过期
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Cache-Control",
        "Transfer-Encoding": "chunked",  # 分块传输
    }
