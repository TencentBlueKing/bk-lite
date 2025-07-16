from libs.metis.graph_core.agent.chatbot_workflow.chatbot_workflow_graph import ChatBotWorkflowGraph
from libs.metis.api.agent.utils import stream_response
from libs.metis.entity.agent.chatbot_workflow.chatbot_workflow_request import ChatBotWorkflowRequest
from libs.metis.services.agent_service import AgentService
import logging
logger = logging.getLogger(__name__)

async def invoke_chatbot_workflow(body: ChatBotWorkflowRequest):
    workflow = ChatBotWorkflowGraph()
    AgentService.set_naive_rag_search_query(body)
    logger.debug(f"执行ChatBotWorkflowGraph,用户的问题:[{body.user_message}]")
    result = await workflow.execute(body)
    response_content = result.model_dump()
    logger.info(
        f"执行ChatBotWorkflowGraph成功,用户的问题:[{body.user_message}]，结果:[{response_content}]")
    return response_content


async def invoke_chatbot_workflow_sse_raw(body: ChatBotWorkflowRequest):
    """
    以SSE格式生成聊天流响应，返回字符串生成器（不依赖web框架，仅Python函数）。
    """
    workflow = ChatBotWorkflowGraph()
    AgentService.set_naive_rag_search_query(body)
    logger.debug(f"执行ChatBotWorkflowGraph,用户的问题:[{body.user_message}]")

    async def sse_generator():
        async for chunk in stream_response(workflow, body, res=None, raw_mode=True):
            yield chunk

    return sse_generator()
