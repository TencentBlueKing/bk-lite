"""ToolsNodes.setup：stdio MCP、远程鉴权头、加载失败不中断。"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.chain.node import ToolsNodes

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_setup_records_stdio_and_remote_and_continues_on_load_errors():
    node = ToolsNodes()
    stdio = SimpleNamespace(
        name="local",
        url="stdio-mcp:local",
        command="python",
        args=["-m", "demo"],
        enable_auth=False,
        transport="",
    )
    remote = SimpleNamespace(
        name="remote",
        url="https://mcp.example/sse",
        command="",
        args=[],
        enable_auth=True,
        auth_token="secret-token",
        transport="sse",
    )
    langchain = SimpleNamespace(
        name="k8s",
        url="langchain:kubernetes",
        extra_tools_prompt="k8s tools",
        extra_param_prompt={},
        enable_auth=False,
        transport="",
    )

    class FakeMCP:
        def __init__(self, cfg):
            self.cfg = cfg

        async def get_tools(self):
            raise RuntimeError("mcp down")

    with (
        patch.object(ToolsNodes, "get_llm_client", return_value="llm"),
        patch("apps.opspilot.metis.llm.chain.node.StructuredOutputParser", return_value="parser"),
        patch("apps.opspilot.metis.llm.chain.node.MultiServerMCPClient", FakeMCP),
        patch(
            "apps.opspilot.metis.llm.chain.node.ToolsLoader.load_tools",
            side_effect=RuntimeError("langchain down"),
        ),
    ):
        await node.setup(SimpleNamespace(tools_servers=[stdio, remote, langchain]))

    assert node.llm == "llm"
    assert node.mcp_config["local"] == {"command": "python", "args": ["-m", "demo"], "transport": "stdio"}
    assert node.mcp_config["remote"]["url"] == "https://mcp.example/sse"
    assert node.mcp_config["remote"]["headers"] == {"Authorization": "secret-token"}
    assert node.tools == []
