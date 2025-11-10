import os

import pytest
from loguru import logger

from neco.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from neco.llm.chain.entity import ToolsServer

NEW_API_KEY = os.getenv('TEST_LLM_API_KEY')
NEW_API_URL = os.getenv('TEST_LLM_API_URL')
TEST_LLM_MODEL = os.getenv('TEST_LLM_MODEL')

TEST_PROMPT = ['现在几点']


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', TEST_PROMPT)
async def test_agui_stream(prompt):
    """测试 agui 协议的 SSE 流式输出"""
    logger.info(f"测试 agui_stream 任务: {prompt}")

    request = ReActAgentRequest(
        openai_api_base=NEW_API_URL,
        openai_api_key=NEW_API_KEY,
        model=TEST_LLM_MODEL,
        user_message=prompt,
        chat_history=[],
        thread_id='test_thread_123',
        tools_servers=[
            ToolsServer(
                name='current_time',
                url='langchain:current_time'
            ),
        ],
    )

    graph = ReActAgentGraph()
    result = graph.agui_stream(request)

    # 打印所有 SSE 事件
    async for sse_event in result:
        print(sse_event, end='')
