import json
from loguru import logger
from neco.llm.agent.lats_agent import LatsAgentRequest, LatsAgentGraph
from neco.sanic.auth.api_auth import auth
from sanic import Blueprint, json
from sanic.response import ResponseStream
from sanic_ext import validate

from src.api.agent.base_agent import BaseAgent
from src.services.agent_service import AgentService

lats_agent_router = Blueprint("lats_agent_router", url_prefix="/agent")


def _prepare_workflow(body: LatsAgentRequest) -> LatsAgentGraph:
    """初始化 workflow"""
    AgentService.prepare_request(body)
    return LatsAgentGraph()


@lats_agent_router.post("/invoke_lats_agent")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent(request, body: LatsAgentRequest):
    """执行 LATS Agent（同步响应）"""
    try:
        workflow = _prepare_workflow(body)
        result = await workflow.execute(body)
        return json(result.model_dump())
    except Exception as e:
        logger.error(f"同步 LATS Agent 失败，问题: {body.user_message}, 错误: {e}")
        raise


@lats_agent_router.post("/invoke_lats_agent_sse")
@auth.login_required
@validate(json=LatsAgentRequest)
async def invoke_lats_agent_sse(request, body: LatsAgentRequest):
    """执行 LATS Agent（流式响应）"""
    workflow = _prepare_workflow(body)

    return ResponseStream(
        lambda res: BaseAgent.stream_response_handler(
            workflow, body, res,
        ),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
