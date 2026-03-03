"""
MCP (Model Context Protocol) 客户端工具类

提供标准的 MCP 协议握手和工具获取功能
"""

import asyncio
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from langchain_mcp_adapters.client import MultiServerMCPClient


class MCPClient:
    """MCP 协议客户端 - 基于 langchain_mcp_adapters"""

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        enable_auth: bool = False,
        auth_token: str = "",
        transport: str = "",
    ):
        """
        初始化 MCP 客户端

        Args:
            server_url: MCP server 地址
            timeout: 请求超时时间（秒）
            enable_auth: 是否启用基本认证
            auth_token: 基本认证的 token (已加密的 Base64 字符串或包含 "Basic " 前缀的完整 Authorization 值)
            transport: 传输协议，可选值：sse / streamable_http；未传时根据 URL 自动判断
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.enable_auth = enable_auth
        self.auth_token = auth_token
        self.transport = transport
        self._mcp_client = None

    def __enter__(self):
        """上下文管理器入口"""
        # 根据 URL 判断传输协议类型
        if self.server_url.startswith("stdio-mcp:"):
            # stdio-mcp: 协议需要 command 和 args，这里抛出错误提示
            raise ValueError("stdio-mcp protocol requires 'command' and 'args' parameters, use dedicated stdio client")

        resolved_transport = self._resolve_transport()

        # 构建服务器配置
        server_config: Dict[str, Any] = {
            "url": self.server_url,
            "timeout": self.timeout,
            "transport": resolved_transport,
        }

        # 添加认证信息
        if self.enable_auth and self.auth_token:
            # 判断 token 格式,支持 Basic 和 Bearer
            if self.auth_token.startswith("Basic ") or self.auth_token.startswith("Bearer "):
                auth_header = self.auth_token
            else:
                # 默认使用 Basic 认证
                auth_header = f"Basic {self.auth_token}"

            server_config["headers"] = {"Authorization": auth_header}

        # 创建 MultiServerMCPClient 实例
        # 注意: langchain_mcp_adapters 0.1.0+ 不支持上下文管理器,直接实例化即可
        self._mcp_client = MultiServerMCPClient({"default": server_config})

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        # MultiServerMCPClient 不需要显式关闭
        pass

    def get_tools(self) -> List[Dict[str, Any]]:
        """
        获取工具列表

        Returns:
            工具列表，每个工具包含 name, description, inputSchema 等字段

        Raises:
            RuntimeError: 获取失败
        """
        if not self._mcp_client:
            raise RuntimeError("MCPClient must be used within a context manager")

        try:
            tools = self._fetch_tools_async()
            return [self._convert_tool_to_dict(tool) for tool in tools]
        except Exception as e:
            raise RuntimeError(f"Failed to get tools: {str(e)}")

    def _fetch_tools_async(self) -> List[Any]:
        """异步获取工具列表，智能复用事件循环"""
        try:
            # 尝试获取已存在的事件循环（如在 async 上下文中）
            loop = asyncio.get_running_loop()
            # 已在异步上下文中，使用 run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(self._mcp_client.get_tools(), loop)
            return future.result(timeout=self.timeout)
        except RuntimeError:
            # 没有运行中的循环，使用 asyncio.run（内部会创建并管理循环）
            return asyncio.run(self._mcp_client.get_tools())

    def _convert_tool_to_dict(self, tool) -> Dict[str, Any]:
        """将工具对象转换为字典格式"""
        tool_dict = {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": {},
        }

        input_schema = self._extract_input_schema(tool)
        if input_schema:
            tool_dict["parameters"] = self._parse_schema_to_parameters(input_schema)

        return tool_dict

    def _resolve_transport(self) -> str:
        """解析传输协议，支持显式指定与 URL 自动识别"""
        explicit_transport = (self.transport or "").strip().lower()
        if explicit_transport in {"sse", "streamable_http"}:
            return explicit_transport

        parsed_url = urlparse(self.server_url)
        query_dict = parse_qs(parsed_url.query)
        query_transport = (query_dict.get("transport", [""])[0] or "").strip().lower()
        if query_transport in {"sse", "streamable_http"}:
            return query_transport

        normalized_path = (parsed_url.path or "").rstrip("/").lower()
        if normalized_path.endswith("/sse"):
            return "sse"
        if normalized_path.endswith("/mcp") or normalized_path.endswith("/streamable_http"):
            return "streamable_http"

        return "sse"

    def _extract_input_schema(self, tool) -> Dict[str, Any]:
        """从工具对象中提取 input schema"""
        if hasattr(tool, "input_schema") and tool.input_schema:
            if isinstance(tool.input_schema, dict):
                return tool.input_schema
            return self._schema_to_input_schema(tool.input_schema)

        if hasattr(tool, "args_schema") and tool.args_schema:
            return self._schema_to_input_schema(tool.args_schema)

        return {}

    def _parse_schema_to_parameters(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """解析 input_schema 并转换为 parameters 格式"""
        if "anyOf" in input_schema:
            return self._parse_anyof_schema(input_schema)
        return self._parse_standard_schema(input_schema)

    def _parse_anyof_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """解析 anyOf 类型的 schema"""
        # 优先级: 有 properties 的 object > $ref > additionalProperties 的 object
        properties, required_fields = self._find_properties_in_anyof(input_schema)

        if not properties:
            properties, required_fields = self._find_ref_in_anyof(input_schema)

        if not properties:
            any_params = self._find_additional_properties_in_anyof(input_schema)
            if any_params:
                return any_params

        return self._build_parameters_dict(properties, required_fields)

    def _find_properties_in_anyof(self, input_schema: Dict[str, Any]) -> tuple:
        """在 anyOf 中查找有 properties 的 object"""
        for option in input_schema.get("anyOf", []):
            if isinstance(option, dict) and option.get("type") == "object" and "properties" in option:
                return option.get("properties", {}), option.get("required", [])
        return {}, []

    def _find_ref_in_anyof(self, input_schema: Dict[str, Any]) -> tuple:
        """在 anyOf 中查找 $ref 引用"""
        for option in input_schema.get("anyOf", []):
            if not isinstance(option, dict) or "$ref" not in option:
                continue

            ref_path = option["$ref"]
            if ref_path.startswith("#/$defs/"):
                ref_name = ref_path.split("/")[-1]
                defs = input_schema.get("$defs", {})
                if ref_name in defs:
                    ref_schema = defs[ref_name]
                    return ref_schema.get("properties", {}), ref_schema.get("required", [])
        return {}, []

    def _find_additional_properties_in_anyof(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """在 anyOf 中查找 additionalProperties 的 object"""
        for option in input_schema.get("anyOf", []):
            if isinstance(option, dict) and option.get("type") == "object" and option.get("additionalProperties"):
                return {
                    "__any__": {
                        "type": "object",
                        "required": False,
                        "description": "This tool accepts any parameters",
                    }
                }
        return {}

    def _parse_standard_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """解析标准的 properties/required 结构"""
        properties = input_schema.get("properties", {})
        required_fields = input_schema.get("required", [])
        return self._build_parameters_dict(properties, required_fields)

    def _build_parameters_dict(self, properties: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
        """构建参数字典"""
        parameters = {}
        for param_name, param_info in properties.items():
            parameters[param_name] = {
                "type": param_info.get("type", "string"),
                "required": param_name in required_fields,
                "description": param_info.get("description", ""),
            }
            # 保留其他字段
            for key in ["default", "enum", "items", "minimum", "maximum", "title"]:
                if key in param_info:
                    parameters[param_name][key] = param_info[key]
        return parameters

    @staticmethod
    def _schema_to_input_schema(args_schema) -> Dict[str, Any]:
        """
        将 Pydantic schema 转换为 MCP inputSchema 格式

        Args:
            args_schema: Pydantic model schema

        Returns:
            MCP inputSchema 格式的字典
        """
        try:
            if hasattr(args_schema, "schema"):
                return args_schema.schema()
            elif hasattr(args_schema, "model_json_schema"):
                return args_schema.model_json_schema()
            else:
                return {}
        except Exception:
            return {}
