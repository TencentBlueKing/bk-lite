from typing import TypedDict, Annotated

from langgraph.graph import add_messages

from neco.llm.chain.entity import BasicLLMRequest, BasicLLMResponse
from neco.llm.chain.graph import BasicGraph
from neco.llm.chain.node import ToolsNodes
from langgraph.constants import END
from langgraph.graph import StateGraph


class DeepAgentRequest(BasicLLMRequest):
    """DeepAgent 请求配置

    DeepAgent 自动提供:
    - 任务规划能力 (write_todos)
    - 文件系统工具 (write_file, read_file)
    - 子代理协作能力
    """
    pass


class DeepAgentResponse(BasicLLMResponse):
    """DeepAgent 响应"""
    pass


class DeepAgentState(TypedDict):
    """DeepAgent 状态"""
    messages: Annotated[list, add_messages]
    graph_request: DeepAgentRequest


class DeepAgentNode(ToolsNodes):
    """DeepAgent 节点"""
    pass


class DeepAgentGraph(BasicGraph):
    """DeepAgent 执行图

    DeepAgent 结合了深度规划、文件管理和子代理协作能力，
    适用于需要复杂推理和多步骤执行的任务。
    """

    async def compile_graph(self, request: DeepAgentRequest):
        """编译 DeepAgent 执行图"""

        # 初始化节点构建器
        node_builder = DeepAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(DeepAgentState)

        # 添加基础图结构
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 使用可复用的 DeepAgent 节点组合构建图
        deep_entry_node = await node_builder.build_deepagent_nodes(
            graph_builder=graph_builder,
            composite_node_name="deep_agent"
        )

        # 连接基础图到 DeepAgent 入口节点
        graph_builder.add_edge(last_edge, deep_entry_node)

        # 编译并返回图
        compiled_graph = graph_builder.compile()

        return compiled_graph
