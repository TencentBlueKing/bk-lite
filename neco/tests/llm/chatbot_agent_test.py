import os
from neco.llm.agent.chatbot_workflow import ChatBotWorkflowGraph,ChatBotWorkflowRequest
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
async def test_chatbot_workflow(prompt):
    logger.info(f"测试任务: {prompt}")
    request = ChatBotWorkflowRequest(
        openai_api_base=NEW_API_URL,
        openai_api_key=NEW_API_KEY,
        model=TEST_LLM_MODEL,
        user_message=prompt,
        chat_history=[],
    )
    graph=ChatBotWorkflowGraph()
    result = await graph.stream(request)
    async for chunk in result:
        content = await graph.filter_messages(chunk)
        print(content, end='', flush=True)

