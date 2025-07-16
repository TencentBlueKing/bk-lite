from typing import Literal, Union, Any

from langgraph.constants import END
from langgraph.graph import StateGraph
import logging
logger = logging.getLogger(__name__)

from libs.metis.graph_core.agent.lats_agent.lats_agent_node import LatsAgentNode
from libs.metis.graph_core.agent.lats_agent.lats_agent_state import LatsAgentState
from libs.metis.graph_core.graph.tools_graph import ToolsGraph
from libs.metis.entity.agent.lats_agent.lats_agent_request import LatsAgentRequest
from libs.metis.entity.agent.lats_agent.lats_agent_response import LatsAgentResponse

class LatsAgentGraph(ToolsGraph):
    """LatsAgent 图执行器

    负责构建和执行 LatsAgent 的计算图，管理节点间的流转逻辑
    """

    async def compile_graph(self, request: LatsAgentRequest) -> StateGraph:
        """编译 LatsAgent 执行图

        Args:
            request: LatsAgent 请求参数

        Returns:
            构建好的状态图
        """
        logger.info("开始编译 LatsAgent 执行图")

        # 初始化节点构建器
        node_builder = LatsAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(LatsAgentState)

        # 添加基础节点
        last_edge = self.prepare_graph(graph_builder, node_builder)
        logger.debug(f"基础图构建完成，最后一个边为: {last_edge}")

        # 添加 LatsAgent 特有节点
        graph_builder.add_node("generate_initial_response",
                               node_builder.generate_initial_response)
        graph_builder.add_node("expand", node_builder.expand)

        # 构建边和条件流转
        graph_builder.add_edge(last_edge, 'generate_initial_response')

        # 添加条件边，使用统一的控制函数
        for node_name in ["generate_initial_response", "expand"]:
            graph_builder.add_conditional_edges(
                node_name,
                node_builder.should_continue,
                ["expand", END]
            )

        # 编译图
        graph = graph_builder.compile()
        logger.info("LatsAgent 执行图编译完成")

        return graph
