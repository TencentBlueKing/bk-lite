import json as json_util
import uuid
from datetime import datetime

from loguru import logger
from neco.llm.agent.chatbot_workflow import ChatBotWorkflowGraph, ChatBotWorkflowRequest
from neco.sanic.auth.api_auth import auth
from sanic import Blueprint, json
from sanic.response import ResponseStream
from sanic_ext import validate

from src.api.agent.base_agent import BaseAgent
from src.services.agent_service import AgentService

chatbot_workflow_api_router = Blueprint(
    "chatbot_workflow_api_router", url_prefix="/agent")


def _prepare_workflow(body: ChatBotWorkflowRequest) -> ChatBotWorkflowGraph:
    """初始化 workflow"""
    AgentService.prepare_request(body)
    return ChatBotWorkflowGraph()


@chatbot_workflow_api_router.post("/invoke_chatbot_workflow")
@auth.login_required
@validate(json=ChatBotWorkflowRequest)
async def invoke_chatbot_workflow(request, body: ChatBotWorkflowRequest):
    """执行 ChatBot Workflow（同步响应）"""
    try:
        workflow = _prepare_workflow(body)
        result = await workflow.execute(body)
        return json(result.model_dump())
    except Exception as e:
        logger.error(f"同步 ChatBot Workflow 失败，问题: {body.user_message}, 错误: {e}")
        raise


@chatbot_workflow_api_router.post("/invoke_chatbot_workflow_sse")
@auth.login_required
@validate(json=ChatBotWorkflowRequest)
async def invoke_chatbot_workflow_sse(request, body: ChatBotWorkflowRequest):
    """执行 ChatBot Workflow（流式响应）"""
    workflow = _prepare_workflow(body)

    return ResponseStream(
        lambda res: BaseAgent.stream_response_handler(
            workflow, body, res,
        ),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
