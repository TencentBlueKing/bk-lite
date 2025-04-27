from langgraph.constants import END
from langgraph.graph import StateGraph

from src.core.graph.tools_graph import ToolsGraph
from src.service.react_agent.entity.react_agent_request import ReActAgentRequest
from src.service.react_agent.entity.react_agent_response import ReActAgentResponse
from src.service.react_agent.node.react_agent_node import ReActAgentNode
from src.service.react_agent.state.react_agent_state import ReActAgentState
from langgraph.pregel import RetryPolicy


class ReActAgentGraph(ToolsGraph):

    async def compile_graph(self, request: ReActAgentRequest):
        node_builder = ReActAgentNode()

        await node_builder.setup(request)

        graph_builder = StateGraph(ReActAgentState)

        last_edge = self.prepare_graph(graph_builder, node_builder)

        tools_node = await node_builder.build_tools_node()
        graph_builder.add_node("tools", tools_node, retry=RetryPolicy(max_attempts=5))
        graph_builder.add_node("agent", node_builder.agent_node, retry=RetryPolicy(max_attempts=5))

        graph_builder.add_edge(last_edge, "agent")
        graph_builder.add_conditional_edges("agent", self.should_continue, ["tools", END])
        graph_builder.add_edge("tools", "agent")

        graph = graph_builder.compile()
        return graph

    async def execute(self, request: ReActAgentRequest) -> ReActAgentResponse:
        graph = await self.compile_graph(request)
        result = await self.invoke(graph, request)
        response = self.parse_basic_response(result)
        return response
