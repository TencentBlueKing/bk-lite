from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

# 规划/执行分步模式下禁止暴露给模型的 DeepAgent 内置能力。
# FS 工具允许在执行步常驻（便于大结果落盘）；write_todos / task / execute 会绕过
# 「按步精确工具可见性」，必须隐藏。
PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS = frozenset(
    {
        "write_todos",
        "task",
        "execute",
    }
)

# 执行步可常驻的 DeepAgent 文件系统工具（总结轮须关闭）。
PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS = frozenset(
    {
        "write_file",
        "read_file",
        "ls",
        "edit_file",
        "glob",
        "glob_search",
        "grep",
        "grep_search",
    }
)

# 若已注册到业务工具池，执行步始终可见（总结轮清空）。
PLANNED_EXECUTION_ALWAYS_ON_BUSINESS_TOOLS = frozenset(
    {
        "knowledge_retrieve",
        "request_user_choice",
        "report_config_diff",
        "generate_repair_report",
    }
)

_PROGRESSIVE_TOOLS_ENV = "OPSPILOT_DEEPAGENT_PROGRESSIVE_TOOLS"
_PROGRESSIVE_TOOLS_FALSE = frozenset({"0", "false", "off", "no"})


def is_progressive_tools_enabled() -> bool:
    """按步工具可见性总开关；默认开启，显式 0/false/off/no 时回退全量 Schema。"""
    raw = os.getenv(_PROGRESSIVE_TOOLS_ENV, "1").strip().lower()
    return raw not in _PROGRESSIVE_TOOLS_FALSE


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        function = tool.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", "") or "")


class ToolVisibilityMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        business_tools: Sequence[BaseTool],
        active_tools: list[BaseTool],
        activator: BaseTool | None = None,
        hidden_tools: set[str] | frozenset[str] | None = None,
        always_visible_tools: set[str] | frozenset[str] | None = None,
        allow_unregistered_tools: bool = True,
        include_always_visible: bool = True,
    ) -> None:
        super().__init__()
        self._business_tool_names = {_tool_name(tool) for tool in business_tools if _tool_name(tool)}
        self._active_tools = active_tools
        self._activator = activator
        self._hidden_tools = frozenset(hidden_tools or ())
        self._always_visible_tools = frozenset(always_visible_tools or ())
        self._allow_unregistered_tools = allow_unregistered_tools
        self.include_always_visible = include_always_visible

    def _filter_request(self, request: ModelRequest) -> ModelRequest:
        visible_business_names = {_tool_name(tool) for tool in self._active_tools if _tool_name(tool)}
        if self._activator is not None:
            visible_business_names.add(_tool_name(self._activator))
        if self.include_always_visible:
            visible_business_names |= self._always_visible_tools

        visible_tools = []
        for tool in request.tools:
            name = _tool_name(tool)
            if name in self._hidden_tools:
                continue
            if not self._allow_unregistered_tools and name not in visible_business_names:
                continue
            if name in self._business_tool_names and name not in visible_business_names:
                continue
            visible_tools.append(tool)
        return request.override(tools=visible_tools)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        return handler(self._filter_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[
            [ModelRequest],
            Awaitable[ModelResponse | AIMessage],
        ],
    ) -> ModelResponse | AIMessage:
        return await handler(self._filter_request(request))
