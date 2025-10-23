from loguru import logger
from neco.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentGraph, PlanAndExecuteAgentRequest
from neco.sanic.auth.api_auth import auth
from sanic import Blueprint, json
from sanic.response import ResponseStream
from sanic_ext import validate

from src.api.agent.base_agent import BaseAgent
from src.services.agent_service import AgentService

plan_and_execute_agent_router = Blueprint(
    "plan_and_execute_agent_router", url_prefix="/agent")


def _prepare_workflow(body: PlanAndExecuteAgentRequest) -> PlanAndExecuteAgentGraph:
    """初始化 workflow"""
    AgentService.prepare_request(body)
    return PlanAndExecuteAgentGraph()


@plan_and_execute_agent_router.post("/invoke_plan_and_execute_agent")
@auth.login_required
@validate(json=PlanAndExecuteAgentRequest)
async def invoke_plan_and_execute_agent(request, body: PlanAndExecuteAgentRequest):
    """执行 Plan and Execute Agent（同步响应）"""
    try:
        workflow = _prepare_workflow(body)

        result = await workflow.execute(body)

        return json(result.model_dump())

    except Exception as e:
        logger.error(f"同步 Plan and Execute Agent 失败，问题: {body.user_message}, 错误: {e}")
        raise


@plan_and_execute_agent_router.post("/invoke_plan_and_execute_agent_sse")
@auth.login_required
@validate(json=PlanAndExecuteAgentRequest)
async def invoke_plan_and_execute_agent_sse(request, body: PlanAndExecuteAgentRequest):
    """执行 Plan and Execute Agent（流式响应）"""
    workflow = _prepare_workflow(body)
    logger.debug(f"执行流式 Plan and Execute Agent，问题: {body.user_message}")

    return ResponseStream(
        lambda res: BaseAgent.stream_response_handler(
            workflow, body, res, 
        ),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )