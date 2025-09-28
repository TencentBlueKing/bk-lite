from sanic.log import logger
from sanic import Blueprint, json
from sanic_ext import validate
from src.core.agent.react_agent.react_agent_graph import ReActAgentGraph
from src.core.sanic_plus.auth.api_auth import auth
from src.web.api.agent.react_agent.react_agent_sse_handler import react_agent_stream_response
from src.web.entity.agent.react_agent.react_agent_request import ReActAgentRequest
from src.web.services.agent_service import AgentService
from sanic.response import ResponseStream

react_agent_api_router = Blueprint(
    "react_agent_api_router", url_prefix="/agent")


@react_agent_api_router.post("/invoke_react_agent")
@auth.login_required
@validate(json=ReActAgentRequest)
async def invoke_react_agent(request, body: ReActAgentRequest):
    graph = ReActAgentGraph()
    AgentService.set_naive_rag_search_query(body)

    logger.debug(f"执行ReActAgentGraph,用户的问题:[{body.user_message}]")
    result = await graph.execute(body)

    response_content = result.model_dump()
    logger.info(
        f"执行ReActAgentGraph成功，用户的问题:[{body.user_message}],结果:[{response_content}]")
    return json(response_content)


@react_agent_api_router.post("/invoke_react_agent_sse")
@auth.login_required
@validate(json=ReActAgentRequest)
async def invoke_react_agent_sse(request, body: ReActAgentRequest):
    workflow = ReActAgentGraph()
    AgentService.set_naive_rag_search_query(body)
    logger.debug(f"执行ReActAgentGraph,用户的问题:[{body.user_message}]")

    return ResponseStream(
        lambda res: react_agent_stream_response(workflow, body, res),
        content_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
