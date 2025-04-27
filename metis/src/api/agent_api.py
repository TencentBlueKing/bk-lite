from loguru import logger
from sanic import Blueprint, json
from sanic_ext import validate

from src.core.web.api_auth import auth
from src.service.chatbot_workflow.entity.chatbot_workflow_request import ChatBotWorkflowRequest
from src.service.chatbot_workflow.graph.chatbot_workflow_graph import ChatBotWorkflowGraph
from src.service.react_agent.entity.react_agent_request import ReActAgentRequest
from src.service.react_agent.graph.react_agent_graph import ReActAgentGraph

agent_api_router = Blueprint("agent", url_prefix="/agent")


@agent_api_router.post("/invoke_chatbot_workflow")
@auth.login_required
@validate(json=ChatBotWorkflowRequest)
def invoke_chatbot_workflow(request, body: ChatBotWorkflowRequest):
    workflow = ChatBotWorkflowGraph()
    for i in body.naive_rag_request:
        i.search_query = body.user_message
    result = workflow.execute(body)
    response_content = result.model_dump()
    logger.info(f"执行ChatBotWorkflowGraph成功,用户的问题:[{body.user_message}]，结果:[{response_content}]")
    return json(response_content)


@agent_api_router.post("/invoke_react_agent")
@auth.login_required
@validate(json=ReActAgentRequest)
async def invoke_react_agent(request, body: ReActAgentRequest):
    graph = ReActAgentGraph()
    for i in body.naive_rag_request:
        i.search_query = body.user_message
    result = await graph.execute(body)
    response_content = result.model_dump()
    logger.info(f"执行ReActGraph成功，用户的问题:[{body.user_message}],结果:[{response_content}]")
    return json(response_content)
