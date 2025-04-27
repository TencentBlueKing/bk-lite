from typing import TypedDict

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from src.core.node.basic_node import BasicNode
from src.tools.tools_loader import ToolsLoader


class ToolsNodes(BasicNode):
    def __init__(self) -> None:
        self.tools = []
        self.mcp_client = None
        self.mcp_config = {}

    async def setup(self, request: BaseModel):
        # 初始化MCP客户端配置
        for server in request.tools_servers:
            if server.url.startswith("langchain:") is False:
                self.mcp_config[server.name] = {
                    "url": server.url,
                    "transport": 'sse'
                }
        self.mcp_client = MultiServerMCPClient(self.mcp_config)
        await self.mcp_client.__aenter__()  # 手动打开连接
        self.tools = self.mcp_client.get_tools()

        # 初始化LangChain工具
        for server in request.tools_servers:
            if server.url.startswith("langchain:") is True:
                langchain_tools = ToolsLoader.load_tools(server.url)
                for tool in langchain_tools:
                    self.tools.append(tool)

    async def agent_node(self, state: TypedDict, config: RunnableConfig) -> TypedDict:
        # 获取完整的消息历史
        messages = state["messages"]

        # 检查最后一条消息，如果是工具消息并且有错误，记录日志
        if messages and isinstance(messages[-1], ToolMessage) and messages[-1].status == 'error':
            print(f"Tool execution error: {messages[-1].content}")

        # 创建一个绑定了工具的LLM
        llm = self.get_llm_client(config["configurable"]["graph_request"])
        llm_with_tools = llm.bind_tools(self.tools)

        # 调用LLM生成回复（可能包含工具调用）
        response = await llm_with_tools.ainvoke(messages)

        # 更新消息列表
        state["messages"].append(response)

        return state

    async def build_tools_node(self) -> ToolNode:
        if self.tools:
            try:
                tool_node = ToolNode(self.tools, handle_tool_errors=True)
                return tool_node
            except Exception as e:
                self.tools = []
                return ToolNode([])
        else:
            return ToolNode([])
