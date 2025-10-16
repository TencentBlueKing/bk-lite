from typing import TypedDict, Annotated, Optional

from langgraph.graph import add_messages

from typing import List

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy
from loguru import logger


class ReActAgentRequest(BasicLLMRequest):
    tools_servers: List[ToolsServer] = []
    langchain_tools: List[str] = []
    max_iterations: int = 10  # ReAct Agent 最大迭代次数

class ReActAgentResponse(BasicLLMResponse):
    pass


class ReActAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: ReActAgentRequest
    react_iteration: Optional[int]  # ReAct Agent 迭代计数
    react_next: Optional[str]  # ReAct Agent 下一个节点

class ReActAgentNode(ToolsNodes):
    pass


class ReActAgentGraph(BasicGraph):
    """ReAct Agent 图执行器 - 使用可复用的 ReAct 节点组合"""

    async def compile_graph(self, request: ReActAgentRequest):
        """编译 ReAct Agent 执行图"""

        # 初始化节点构建器
        node_builder = ReActAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(ReActAgentState)

        # 添加基础图结构
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 使用可复用的 ReAct 节点组合构建图
        react_entry_node = await node_builder.build_react_nodes(
            graph_builder=graph_builder,
            composite_node_name="react_agent",
            additional_system_prompt=request.system_message_prompt,
            next_node=END
        )

        # 连接基础图到 ReAct 入口节点
        graph_builder.add_edge(last_edge, react_entry_node)

        # 编译并返回图
        compiled_graph = graph_builder.compile()

        return compiled_graph
