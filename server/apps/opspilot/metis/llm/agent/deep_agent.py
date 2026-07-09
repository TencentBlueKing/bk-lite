from typing import TypedDict, Annotated, Optional

from langgraph.graph import add_messages

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from apps.opspilot.metis.llm.chain.graph import BasicGraph
from apps.opspilot.metis.llm.chain.node import ToolsNodes
from langgraph.constants import END
from langgraph.graph import StateGraph


class DeepAgentRequest(BasicLLMRequest):
    pass


class DeepAgentResponse(BasicLLMResponse):
    pass


class DeepAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: DeepAgentRequest


class DeepAgentNode(ToolsNodes):
    pass


class DeepAgentGraph(BasicGraph):
    """DeepAgent 执行图。

    deepagents 是 OpsPilot 当前唯一 Agent runtime：原生规划、虚拟文件系统、
    子代理、上下文压缩、技能（SKILL.md）与人工审批均通过该图接入。
    """

    async def compile_graph(self, request: DeepAgentRequest):
        """编译 DeepAgent 执行图"""

        node_builder = DeepAgentNode()
        import logging as _dg; _dg.warning("DEBUG_DG: about to call setup")
        await node_builder.setup(request)

        graph_builder = StateGraph(DeepAgentState)

        last_edge = self.prepare_graph(graph_builder, node_builder)

        deep_entry_node = await node_builder.build_deepagent_nodes(
            graph_builder=graph_builder,
            composite_node_name="deep_agent",
        )

        graph_builder.add_edge(last_edge, deep_entry_node)
        return graph_builder.compile()
