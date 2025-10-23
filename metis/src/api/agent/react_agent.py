from loguru import logger
from neco.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from neco.sanic.auth.api_auth import auth
from sanic import Blueprint, json
from sanic.response import ResponseStream
from sanic_ext import validate

from src.api.agent.base_agent import BaseAgent
from src.services.agent_service import AgentService

react_agent_api_router = Blueprint(
    "react_agent_api_router", url_prefix="/agent")


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
        result = await workflow.execute(body)
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

    return ResponseStream(
        lambda res: BaseAgent.stream_response_handler(
            workflow, body, res,
        ),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
