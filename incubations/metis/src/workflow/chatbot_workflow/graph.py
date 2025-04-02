import os

from langgraph.constants import START, END
from langgraph.graph import StateGraph

from src.workflow.chatbot_workflow.entity import ChatBotWorkflowRequest, ChatBotWorkflowResponse
from src.workflow.chatbot_workflow.nodes import ChatBotWorkflowNode
from src.workflow.chatbot_workflow.state import ChatBotWorkflowState
from langgraph.checkpoint.postgres import PostgresSaver


class ChatBotWorkflowGraph():
    def __init__(self, request: ChatBotWorkflowRequest):
        self.request = request

        node_builder = ChatBotWorkflowNode(self.request)
        graph_builder = StateGraph(ChatBotWorkflowState)
        graph_builder.add_node("init_request_node", node_builder.init_request_node)
        graph_builder.add_node("prompt_message_node", node_builder.prompt_message_node)
        graph_builder.add_node("add_chat_history_node", node_builder.add_chat_history_node)
        graph_builder.add_node("chatbot_node", node_builder.chatbot_node)
        graph_builder.add_node("naive_rag_node", node_builder.naive_rag_node)

        graph_builder.add_edge(START, "init_request_node")
        graph_builder.add_edge("init_request_node", "prompt_message_node")
        graph_builder.add_edge("prompt_message_node", "add_chat_history_node")
        graph_builder.add_edge("add_chat_history_node", "naive_rag_node")
        graph_builder.add_edge("naive_rag_node", "chatbot_node")
        graph_builder.add_edge("chatbot_node", END)

        graph = graph_builder.compile()
        self.graph = graph

    def invoke(self) -> ChatBotWorkflowResponse:
        if self.request.thread_id:
            config = {
                "configurable":
                    {
                        "thread_id": self.request.thread_id,
                        "user_id": self.request.user_id
                    }
            }
            with PostgresSaver.from_conn_string(os.getenv('DB_URI')) as checkpoint:
                self.graph.checkpoint = checkpoint
                result = self.graph.invoke(self.request, config)
        else:
            result = self.graph.invoke(self.request)

        response = ChatBotWorkflowResponse(message=result["messages"][-1].content,
                                           total_tokens=result["messages"][-1].response_metadata['token_usage'][
                                               'total_tokens'])
        return response
