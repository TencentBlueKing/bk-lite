from venv import logger
from libs.metis.graph_core.agent.react_agent.react_agent_graph import ReActAgentGraph
from libs.metis.api.agent.utils import stream_response
from libs.metis.entity.agent.chatbot_workflow.chatbot_workflow_request import ChatBotWorkflowRequest
from libs.metis.entity.agent.react_agent.react_agent_request import ReActAgentRequest
from libs.metis.services.agent_service import AgentService

import logging
logger = logging.getLogger(__name__)

async def invoke_react_agent(body: ReActAgentRequest):
    graph = ReActAgentGraph()
    AgentService.set_naive_rag_search_query(body)

    logger.debug(f"执行ReActAgentGraph,用户的问题:[{body.user_message}]")
    result = await graph.execute(body)

    response_content = result.model_dump()
    logger.info(
        f"执行ReActAgentGraph成功，用户的问题:[{body.user_message}],结果:[{response_content}]")
    return response_content


async def invoke_react_agent_sse( body: ReActAgentRequest):
    workflow = ReActAgentGraph()
    AgentService.set_naive_rag_search_query(body)
    logger.debug(f"执行ReActAgentGraph,用户的问题:[{body.user_message}]")

    async def sse_generator():
        async for chunk in stream_response(workflow, body, res=None, raw_mode=True):
            yield chunk

    return sse_generator()