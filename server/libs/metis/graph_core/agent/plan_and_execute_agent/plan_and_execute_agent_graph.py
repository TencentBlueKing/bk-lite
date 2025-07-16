from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.pregel import RetryPolicy
import logging
logger = logging.getLogger(__name__)

from libs.metis.graph_core.agent.plan_and_execute_agent.plan_and_execute_agent_node import PlanAndExecuteAgentNode
from libs.metis.graph_core.agent.plan_and_execute_agent.plan_and_execute_agent_state import PlanAndExecuteAgentState
from libs.metis.entity.basic.basic_llm_response import BasicLLMResponse
from libs.metis.graph_core.graph.tools_graph import ToolsGraph
from libs.metis.entity.agent.plan_and_execute_agent.plan_and_execute_agent_request import PlanAndExecuteAgentRequest
from libs.metis.entity.agent.plan_and_execute_agent.plan_and_execute_agent_response import PlanAndExecuteAgentResponse


class PlanAndExecuteAgentGraph(ToolsGraph):
    """Plan and Execute Agent的图实现

    负责构建和执行Plan and Execute智能体的工作流图
    """

    async def compile_graph(self, request: PlanAndExecuteAgentRequest):
        """编译工作流图

        Args:
            request: 计划执行代理请求

        Returns:
            编译后的图
        """
        # 创建节点构建器
        node_builder = PlanAndExecuteAgentNode()
        logger.info(f"初始化Plan and Execute Agent图，设置工具和请求")

        # 设置节点构建器
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(PlanAndExecuteAgentState)
        logger.info(f"创建Plan and Execute Agent状态图")

        # 准备基本图结构
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 添加Plan and Execute特定节点
        graph_builder.add_node("agent", node_builder.execute_step,
                               retry=RetryPolicy(max_attempts=5))
        graph_builder.add_node("planner", node_builder.plan_step)
        graph_builder.add_node("replan", node_builder.replan_step)

        # 设置图边缘
        graph_builder.add_edge(last_edge, "planner")
        graph_builder.add_edge("planner", "agent")
        graph_builder.add_conditional_edges(
            "agent",
            node_builder.should_end,
            {
                "agent": "agent",  # 继续执行下一步
                "replan": "replan",  # 重新规划
                END: END,  # 结束执行
            }
        )
        graph_builder.add_conditional_edges(
            "replan",
            node_builder.should_end,
            {
                "agent": "agent",  # 继续执行新计划
                "replan": "replan",  # 继续重新规划
                END: END,  # 结束执行
            }
        )

        # 编译图
        logger.info(f"编译Plan and Execute Agent图")
        graph = graph_builder.compile()
        return graph
