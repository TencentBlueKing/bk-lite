import os

from dotenv import load_dotenv
from loguru import logger

from src.core.entity.chat_history import ChatHistory
from src.rag.native_rag.entity.elasticsearch_retriever_request import ElasticSearchRetrieverRequest
from src.service.chatbot_workflow.entity.chatbot_workflow_request import ChatBotWorkflowRequest
from src.service.chatbot_workflow.graph.chatbot_workflow_graph import ChatBotWorkflowGraph


def test_chat():
    request = ChatBotWorkflowRequest(
        model="gpt-4o",
        openai_api_base=os.getenv("OPENAI_BASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        user_message="你是谁",
        system_message_prompt="你是一个智能运维机器人，名字叫Metis",
        user_id="1",
        thread_id="2"
    )
    workflow = ChatBotWorkflowGraph()
    result = workflow.execute(request)
    logger.info(result)


def test_chat_with_naiverag():
    user_message = "你好"

    request = ChatBotWorkflowRequest(
        model="gpt-4o",
        openai_api_base=os.getenv("OPENAI_BASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        user_message=user_message,
        system_message_prompt="你是一个智能运维机器人，名字叫Metis",
        user_id="1",
        thread_id="2",
        enable_naive_rag=True,
        naive_rag_request=[]
    )
    workflow = ChatBotWorkflowGraph()
    result = workflow.execute(request)
    print(result)


def test_chat_with_manunal_chat_history():
    request = ChatBotWorkflowRequest(
        model="gpt-4o",
        openai_api_base=os.getenv("OPENAI_BASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        user_message="我们聊了几轮对话了",
        system_message_prompt="你是一个智能运维机器人，名字叫Metis",
        chat_history=[
            ChatHistory(event='user', message='你是谁'),
            ChatHistory(event='assistant', message='我是一个智能运维机器人，名字叫Metis'),
            ChatHistory(event='user', message='你能做什么'),
            ChatHistory(event='assistant', message='我能帮助你解决运维问题'),
        ]
    )
    workflow = ChatBotWorkflowGraph()
    result = workflow.execute(request)
    logger.info(result)
