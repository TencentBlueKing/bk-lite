from typing import TypedDict

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.core.entity.basic_llm_request import BasicLLMReuqest
from src.rag.native_rag.rag.elasticsearch_rag import ElasticSearchRag


class BasicNode:

    def get_llm_client(self, request: BasicLLMReuqest) -> ChatOpenAI:
        llm = ChatOpenAI(model=request.model, base_url=request.openai_api_base,
                         api_key=request.openai_api_key, temperature=request.temperature)
        return llm

    def prompt_message_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        if config["configurable"]["graph_request"].system_message_prompt:
            state["messages"].append(
                SystemMessage(content=config["configurable"]["graph_request"].system_message_prompt)
            )
        return state

    def add_chat_history_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        if config["configurable"]['graph_request'].chat_history:
            for chat in config["configurable"]['graph_request'].chat_history:
                if chat.event == 'user':
                    if chat.image_data:
                        state['messages'].append(HumanMessage(content=[
                            {"type": "text", "text": "describe the weather in this image"},
                            {"type": "image_url", "image_url": {"url": chat.image_data}},
                        ]))
                    else:
                        state['messages'].append(HumanMessage(content=chat.message))
                elif chat.event == 'assistant':
                    state['messages'].append(AIMessage(content=chat.message))
        return state

    def naive_rag_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        if config["configurable"]['graph_request'].enable_naive_rag is False:
            return state

        naive_rag_request = config["configurable"]["graph_request"].naive_rag_request
        if len(naive_rag_request) == 0:
            return state

        for rag_search_request in naive_rag_request:
            elasticsearch_rag = ElasticSearchRag()
            rag_result = elasticsearch_rag.search(rag_search_request)
            rag_message = "以下是提供给你参考的背景信息：\n"
            for r in rag_result:
                rag_message += f"""
                    Title: {r.metadata['_source']['metadata']['knowledge_title']}
                    Chunk: {r.page_content}
                """
            state["messages"].append(HumanMessage(content=rag_message))
        return state

    def user_message_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        state["messages"].append(HumanMessage(content=config["configurable"]["graph_request"].user_message))
        return state

    def chatbot_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        message = state["messages"]
        message.append(config["configurable"]["graph_request"].user_message)
        llm = self.get_llm_client(config["configurable"]["graph_request"])
        return {
            "messages": [
                llm.invoke(message)
            ]
        }

        return execute
