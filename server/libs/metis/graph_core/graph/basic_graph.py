import os
import uuid
from abc import ABC, abstractmethod

import tiktoken
from langchain_core.messages import AIMessageChunk, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.constants import START

from libs.metis.entity.basic.basic_llm_request import BasicLLMRequest
from libs.metis.entity.basic.basic_llm_response import BasicLLMResponse
from config.components.metis import METIS_DB_URL


class BasicGraph(ABC):
    def count_tokens(self, text: str, encoding_name='gpt-4o') -> int:
        try:
            encoding = tiktoken.encoding_for_model(
                encoding_name)  # 获取模型的 Token 编码器
            tokens = encoding.encode(text)  # 将文本 Token 化
            return len(tokens)  # 返回 Token 数量
        except KeyError:
            # 如果模型名称不支持，回退到默认的编码方式
            print(f"模型 {encoding_name} 不支持。默认回退到通用编码器。")
            encoding = tiktoken.get_encoding("cl100k_base")  # 通用编码器
            tokens = encoding.encode(text)
            return len(tokens)

    async def aprint_chunk(self, result):
        async for chunk in result:
            if isinstance(chunk[0], AIMessageChunk):
                print(chunk[0].content, end='', flush=True)
        print('\n')

    def print_chunk(self, result):
        for chunk in result:
            if type(chunk[0]) == AIMessageChunk:
                print(chunk[0].content, end='', flush=True)
        print('\n')

    def prepare_graph(self, graph_builder, node_builder) -> str:
        graph_builder.add_node("prompt_message_node",
                               node_builder.prompt_message_node)
        graph_builder.add_node("add_chat_history_node",
                               node_builder.add_chat_history_node)
        graph_builder.add_node("naive_rag_node", node_builder.naive_rag_node)
        graph_builder.add_node("user_message_node",
                               node_builder.user_message_node)

        graph_builder.add_edge(START, "prompt_message_node")
        graph_builder.add_edge("prompt_message_node", "add_chat_history_node")
        graph_builder.add_edge("add_chat_history_node", "naive_rag_node")
        graph_builder.add_edge("naive_rag_node", "user_message_node")

        return 'user_message_node'

    async def invoke(self, graph, request: BasicLLMRequest, stream_mode='values'):
        config = {
            "graph_request": request,
            "recursion_limit": 10,
            "trace_id": str(uuid.uuid4()),
            "configurable": {
                **request.extra_config,
            }
        }

        if request.thread_id:
            config['configurable'] = {
                "thread_id": request.thread_id,
                "user_id": request.user_id,
                "trace_id": str(uuid.uuid4()),
                **(config['configurable'] or {})
            }
            with PostgresSaver.from_conn_string(METIS_DB_URL) as checkpoint:
                graph.checkpoint = checkpoint

        if stream_mode == 'values':
            result = await graph.ainvoke(request, config)
            return result

        if stream_mode == 'messages':
            result = graph.astream(request, config, stream_mode=stream_mode)
            return result

    @abstractmethod
    async def compile_graph(self, request: BasicLLMRequest):
        pass

    async def stream(self, request: BasicLLMRequest):
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request, stream_mode='messages')
        return result

    async def execute(self, request: BasicLLMRequest) -> BasicLLMResponse:
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request)

        prompt_token = 0
        completion_token = 0

        for i in result["messages"]:
            if type(i) == AIMessage and 'token_usage' in i.response_metadata:
                prompt_token += i.response_metadata['token_usage']['prompt_tokens']
                completion_token += i.response_metadata['token_usage']['completion_tokens']
        response = BasicLLMResponse(message=result["messages"][-1].content,
                                    total_tokens=prompt_token + completion_token,
                                    prompt_tokens=prompt_token,
                                    completion_tokens=completion_token)

        return response
