

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import BasicNode
from neco.llm.chain.state import BasicState
from langgraph.types import RetryPolicy
from langgraph.constants import END
from langgraph.graph import StateGraph

class ChatBotWorkflowRequest(BasicLLMRequest):
    pass

class ChatBotWorkflowResponse(BasicLLMResponse):
    pass

class ChatBotWorkflowState(BasicState):
    graph_request: ChatBotWorkflowRequest

class ChatBotWorkflowNode(BasicNode):
    pass

class ChatBotWorkflowGraph(BasicGraph):

    async def compile_graph(self, request: BasicLLMRequest):
        graph_builder = StateGraph(ChatBotWorkflowState)
        node_builder = ChatBotWorkflowNode()

        last_edge = self.prepare_graph(graph_builder, node_builder)
        graph_builder.add_node(
            "chat_node", node_builder.chat_node, retry=RetryPolicy(max_attempts=5))

        graph_builder.add_edge(last_edge, "chat_node")
        graph_builder.add_edge("chat_node", END)

        graph = graph_builder.compile()
        return graph
    