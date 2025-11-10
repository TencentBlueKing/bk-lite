import os
from neco.llm.agent.plan_and_execute_agent import PlanAndExecuteAgentGraph, PlanAndExecuteAgentRequest
from neco.llm.chain.entity import ToolsServer
import pytest
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

NEW_API_KEY = os.getenv('TEST_LLM_API_KEY')
NEW_API_URL = os.getenv('TEST_LLM_API_URL')
TEST_LLM_MODEL = os.getenv('TEST_LLM_MODEL')

TEST_PROMPT = [
    # '分析https://github.com/TencentBlueKing/bk-lite仓库今天的提交情况',
    '现在几点'
]


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', TEST_PROMPT)
async def test_plan_and_execute_agent(prompt):
    request = PlanAndExecuteAgentRequest(
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
    graph = PlanAndExecuteAgentGraph()
    result = graph.agui_stream(request)

    # 打印所有 SSE 事件
    async for sse_event in result:
        print(sse_event, end='')
