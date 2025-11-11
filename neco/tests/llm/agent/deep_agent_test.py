import os
from neco.llm.agent.deep_agent import DeepAgentGraph, DeepAgentRequest
from neco.llm.chain.entity import ToolsServer
import pytest
from loguru import logger

NEW_API_KEY = os.getenv('TEST_LLM_API_KEY')
NEW_API_URL = os.getenv('TEST_LLM_API_URL')
TEST_LLM_MODEL = os.getenv('TEST_LLM_MODEL')

TEST_PROMPT = [
    # DeepAgent 适合需要深度规划和多步骤执行的复杂任务
    '基于现在的时间点去思考，锐评 langchain 框架的优缺点，并给出改进建议',
    # '简要介绍LangGraph的核心概念(200字以内)'
]


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', TEST_PROMPT)
async def test_deep_agent(prompt):
    logger.info(f"测试任务: {prompt}")
    request = DeepAgentRequest(
        openai_api_base=NEW_API_URL,
        openai_api_key=NEW_API_KEY,
        model=TEST_LLM_MODEL,
        user_message=prompt,
        chat_history=[],
        tools_servers=[
            ToolsServer(
                name='current_time',
                url='langchain:current_time'
            ),
            ToolsServer(
                name='duckduckgo',
                url='langchain:duckduckgo'
            ),
            ToolsServer(
                name='shell',
                url='langchain:shell'
            )
        ],
    )
    graph = DeepAgentGraph()
    result = graph.agui_stream(request)

    # 打印所有 SSE 事件
    async for sse_event in result:
        print(sse_event, end='')
