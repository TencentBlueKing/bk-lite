from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from libs.metis.graph_core.node.basic_node import BasicNode
from libs.metis.tools.tools_loader import ToolsLoader


class ToolsNodes(BasicNode):
    def __init__(self) -> None:
        self.tools = []
        self.mcp_client = None
        self.mcp_config = {}
        self.tools_prompt_tokens = 0
        self.tools_completions_tokens = 0

    async def setup(self, request: BaseModel):
        # 初始化MCP客户端配置
        for server in request.tools_servers:
            if server.url.startswith("langchain:") is False:
                self.mcp_config[server.name] = {
                    "url": server.url,
                    "transport": 'sse'
                }
        self.mcp_client = MultiServerMCPClient(self.mcp_config)
        self.tools = await self.mcp_client.get_tools()

        # 初始化LangChain工具
        for server in request.tools_servers:
            if server.url.startswith("langchain:") is True:
                langchain_tools = ToolsLoader.load_tools(server)
                for tool in langchain_tools:
                    self.tools.append(tool)

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
