from typing import TypedDict, Annotated, Optional

from langgraph.graph import add_messages

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest, BasicLLMResponse, ToolsServer
from apps.opspilot.metis.llm.chain.graph import BasicGraph
from apps.opspilot.metis.llm.chain.node import ToolsNodes
from langgraph.constants import END
from langgraph.graph import StateGraph


class ReActAgentRequest(BasicLLMRequest):
    pass


class ReActAgentResponse(BasicLLMResponse):
    pass


class ReActAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    graph_request: ReActAgentRequest


class ReActAgentNode(ToolsNodes):
    pass


class ReActAgentGraph(BasicGraph):
    """ReAgent 执行图。

    名称保留为 ReAct，但执行引擎已升级为 deepagents（create_deep_agent）：
    原生规划、虚拟文件系统、子代理、上下文压缩、Anthropic prompt 缓存，
    并真实接入 tools/MCP、knowledge_retrieve 工具、SKILL.md 技能（MinIO backend）
    与人工审批（interrupt_on）。详见 ToolsNodes.build_deepagent_nodes。
    """

    async def compile_graph(self, request: ReActAgentRequest):
        """编译 ReAgent（DeepAgent 引擎）执行图"""

        # 初始化节点构建器（加载 tools/MCP -> self.tools / self.all_tools）
        node_builder = ReActAgentNode()
        await node_builder.setup(request)

        # 创建状态图
        graph_builder = StateGraph(ReActAgentState)

        # 添加基础图结构（prompt / 历史 / user_message / 可选预检索）
        last_edge = self.prepare_graph(graph_builder, node_builder)

        # 统一 DeepAgent 引擎入口
        deep_entry_node = await node_builder.build_deepagent_nodes(
            graph_builder=graph_builder,
            composite_node_name="react_agent",
        )

        # 连接基础图到 DeepAgent 入口节点
        graph_builder.add_edge(last_edge, deep_entry_node)

        # 编译并返回图
        compiled_graph = graph_builder.compile()

        return compiled_graph
