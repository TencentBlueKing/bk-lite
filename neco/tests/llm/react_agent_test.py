import os
from neco.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from neco.llm.chain.entity import ToolsServer
import pytest
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

NEW_API_KEY=os.getenv('TEST_LLM_API_KEY')
NEW_API_URL=os.getenv('TEST_LLM_API_URL')
TEST_LLM_MODEL=os.getenv('TEST_LLM_MODEL')

TEST_PROMPT = [
    # '分析https://github.com/TencentBlueKing/bk-lite仓库今天的提交情况',
    '现在几点'
]

@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', TEST_PROMPT)
async def test_react_agent(prompt):
    logger.info(f"测试任务: {prompt}")
    request = ReActAgentRequest(
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
                name='github',
                url='langchain:github'
            )
        ],
    )
    graph=ReActAgentGraph()
    result = await graph.stream(request)
    async for chunk in result:
        content = await graph.filter_messages(chunk)
        print(content, end='', flush=True)

