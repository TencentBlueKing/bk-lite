import json as json_util
import uuid
from datetime import datetime

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from loguru import logger
from neco.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from neco.sanic.auth.api_auth import auth
from sanic import Blueprint, json
from sanic.response import ResponseStream
from sanic_ext import validate

from src.services.agent_service import AgentService

react_agent_api_router = Blueprint(
    "react_agent_api_router", url_prefix="/agent")


def _create_sse_message(chat_id: str, model: str, created: int,
                        prompt_tokens: int, completion_tokens: int,
                        delta_content: str = None, finish_reason: str = None) -> dict:
    """构建 SSE 消息块"""
    message = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant"} if delta_content is None and finish_reason is None else {},
            "finish_reason": finish_reason
        }]
    }

    if delta_content is not None:
        message["choices"][0]["delta"]["content"] = delta_content

    return message


async def _write_sse(response, data: dict):
    """写入 SSE 格式数据"""
    content = f"data: {json_util.dumps(data, ensure_ascii=False)}\n\n"
    await response.write(content.encode('utf-8'))


async def react_agent_stream_response(workflow: ReActAgentGraph,
                                      body: ReActAgentRequest,
                                      response: ResponseStream):
    """流式响应处理器"""
    chat_id = str(uuid.uuid4())
    created = int(datetime.now().timestamp())
    prompt_tokens = 0
    completion_tokens = 0

    try:
        # 发送初始消息
        await _write_sse(
            response,
            _create_sse_message(chat_id, body.model, created,
                                prompt_tokens, completion_tokens)
        )

        # 流式处理
        result = await workflow.stream(body)
        async for chunk in result:
            msg = chunk[0]

            # 处理工具调用消息
            if isinstance(msg, ToolMessage):
                content = f"🔧 执行工具[{msg.name}]\n\n"
                await _write_sse(
                    response,
                    _create_sse_message(chat_id, body.model, created,
                                        prompt_tokens, completion_tokens,
                                        delta_content=content)
                )

            # 处理助手消息
            elif isinstance(msg, (AIMessage, AIMessageChunk)):
                content = msg.content
                completion_tokens += workflow.count_tokens(content)
                await _write_sse(
                    response,
                    _create_sse_message(chat_id, body.model, created,
                                        prompt_tokens, completion_tokens,
                                        delta_content=content)
                )

            # 统计输入 token
            else:
                try:
                    prompt_tokens += workflow.count_tokens(msg.content)
                except AttributeError:
                    pass

        # 发送结束标记
        await _write_sse(
            response,
            _create_sse_message(chat_id, body.model, created,
                                prompt_tokens, completion_tokens,
                                finish_reason="stop")
        )
        await response.write("data: [DONE]\n\n".encode('utf-8'))

        logger.info(f"流式响应完成，问题: {body.user_message}, "
                    f"tokens: {prompt_tokens}/{completion_tokens}")

    except Exception as e:
        logger.error(f"流式响应失败，问题: {body.user_message}, 错误: {e}")
        raise


def _prepare_workflow(body: ReActAgentRequest) -> ReActAgentGraph:
    """初始化 workflow"""
    AgentService.prepare_request(body)
    return ReActAgentGraph()


@react_agent_api_router.post("/invoke_react_agent")
@auth.login_required
@validate(json=ReActAgentRequest)
async def invoke_react_agent(request, body: ReActAgentRequest):
    """执行 ReAct Agent（同步响应）"""
    try:
        workflow = _prepare_workflow(body)
        logger.debug(f"执行同步 ReAct Agent，问题: {body.user_message}")

        result = await workflow.execute(body)

        logger.info(f"同步 ReAct Agent 完成，问题: {body.user_message}")
        return json(result.model_dump())

    except Exception as e:
        logger.error(f"同步 ReAct Agent 失败，问题: {body.user_message}, 错误: {e}")
        raise


@react_agent_api_router.post("/invoke_react_agent_sse")
@auth.login_required
@validate(json=ReActAgentRequest)
async def invoke_react_agent_sse(request, body: ReActAgentRequest):
    """执行 ReAct Agent（流式响应）"""
    workflow = _prepare_workflow(body)
    logger.debug(f"执行流式 ReAct Agent，问题: {body.user_message}")

    return ResponseStream(
        lambda res: react_agent_stream_response(workflow, body, res),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
