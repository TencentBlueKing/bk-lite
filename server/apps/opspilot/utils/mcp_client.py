"""
MCP (Model Context Protocol) 客户端工具类

提供标准的 MCP 协议握手和工具获取功能
"""
from typing import Any, Dict, List, Optional

import httpx


class MCPClient:
    """MCP 协议客户端"""

    def __init__(self, server_url: str, timeout: float = 30.0):
        """
        初始化 MCP 客户端

        Args:
            server_url: MCP server 地址
            timeout: 请求超时时间（秒）
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._client: Optional[httpx.Client] = None

    def __enter__(self):
        """上下文管理器入口"""
        self._client = httpx.Client(timeout=self.timeout)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if self._client:
            self._client.close()

    def _get_common_headers(self) -> Dict[str, str]:
        """获取公共请求头"""
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        return headers

    def _post(self, payload: Dict[str, Any]) -> httpx.Response:
        """发送 POST 请求"""
        if not self._client:
            raise RuntimeError("MCPClient must be used within a context manager")

        return self._client.post(self.server_url, json=payload, headers=self._get_common_headers())

    def initialize(self) -> Dict[str, Any]:
        """
        步骤1: 发送 initialize 请求并获取 session ID

        Returns:
            服务器返回的初始化信息（包含 protocolVersion, capabilities, serverInfo）

        Raises:
            RuntimeError: 初始化失败或未返回 session ID
            httpx.HTTPStatusError: HTTP 请求失败
        """
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "bklite", "version": "1.0.0"}},
        }

        response = self._post(init_payload)

        if response.status_code != 200:
            raise RuntimeError(f"Initialize failed: {response.text}")

        # 获取 session ID
        self.session_id = response.headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("MCP server did not return session ID")

        return response.json().get("result", {})

    def send_initialized_notification(self) -> None:
        """
        步骤2: 发送 initialized 通知

        必须在 initialize 之后调用
        """
        if not self.session_id:
            raise RuntimeError("Must call initialize() before sending notifications")

        notification_payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}

        self._post(notification_payload)

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        步骤3: 获取工具列表

        必须在 initialize 和 send_initialized_notification 之后调用

        Returns:
            工具列表，每个工具包含 name, description, input_schema 等字段

        Raises:
            RuntimeError: 请求失败或服务器返回错误
        """
        if not self.session_id:
            raise RuntimeError("Must call initialize() before listing tools")

        tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

        response = self._post(tools_payload)

        if response.status_code not in [200, 202]:
            raise RuntimeError(f"Failed to fetch tools: {response.text}")

        if not response.text.strip():
            raise RuntimeError("MCP server returned empty response")

        response_data = response.json()

        # 处理错误响应
        if "error" in response_data:
            error_msg = response_data["error"].get("message", "Unknown error")
            error_code = response_data["error"].get("code", "")
            raise RuntimeError(f"MCP server error [{error_code}]: {error_msg}")

        return response_data.get("result", {}).get("tools", [])

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        完整的 MCP 握手流程并获取工具列表

        执行标准的三步握手：
        1. initialize - 建立连接并获取 session ID
        2. notifications/initialized - 通知服务器初始化完成
        3. tools/list - 请求工具列表

        Returns:
            工具列表

        Raises:
            RuntimeError: 任何步骤失败
            httpx.RequestError: 网络请求失败
            json.JSONDecodeError: 响应解析失败
        """
        self.initialize()
        self.send_initialized_notification()
        return self.list_tools()
