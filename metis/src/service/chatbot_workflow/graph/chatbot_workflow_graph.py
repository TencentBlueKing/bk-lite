from langgraph.constants import END
from langgraph.graph import StateGraph

from src.core.graph.basic_graph import BasicGraph
from src.service.chatbot_workflow.entity.chatbot_workflow_request import ChatBotWorkflowRequest
from src.service.chatbot_workflow.entity.chatbot_workflow_response import ChatBotWorkflowResponse
from src.service.chatbot_workflow.node.chatbot_workflow_node import ChatBotWorkflowNode
from src.service.chatbot_workflow.state.chatbot_workflow_state import ChatBotWorkflowState
from langgraph.pregel import RetryPolicy


class ChatBotWorkflowGraph(BasicGraph):

    def compile_graph(self):
        graph_builder = StateGraph(ChatBotWorkflowState)
        node_builder = ChatBotWorkflowNode()

        last_edge = self.prepare_graph(graph_builder, node_builder)
        graph_builder.add_node(
            "chatbot_node", node_builder.chatbot_node, retry=RetryPolicy(max_attempts=5))

        graph_builder.add_edge(last_edge, "chatbot_node")
        graph_builder.add_edge("chatbot_node", END)

        graph = graph_builder.compile()
        return graph

    def execute(self, request: ChatBotWorkflowRequest) -> ChatBotWorkflowResponse:
        graph = self.compile_graph()
        result = self.invoke(graph, request)
        response = self.parse_basic_response(result)
        return response
