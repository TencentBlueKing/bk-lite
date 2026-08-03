from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool


PLANNED_EXECUTION_HIDDEN_DEEPAGENT_TOOLS = frozenset(
    {
        "write_todos",
        "write_file",
        "read_file",
        "ls",
        "edit_file",
        "glob",
        "glob_search",
        "grep",
        "grep_search",
        "task",
        "execute",
    }
)


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
        allow_unregistered_tools: bool = True,
    ) -> None:
        super().__init__()
        self._business_tool_names = {
            _tool_name(tool)
            for tool in business_tools
            if _tool_name(tool)
        }
        self._active_tools = active_tools
        self._activator = activator
        self._hidden_tools = frozenset(hidden_tools or ())
        self._allow_unregistered_tools = allow_unregistered_tools

    def _filter_request(self, request: ModelRequest) -> ModelRequest:
        visible_business_names = {
            _tool_name(tool)
            for tool in self._active_tools
            if _tool_name(tool)
        }
        if self._activator is not None:
            visible_business_names.add(_tool_name(self._activator))

        visible_tools = []
        for tool in request.tools:
            name = _tool_name(tool)
            if name in self._hidden_tools:
                continue
            if not self._allow_unregistered_tools and name not in visible_business_names:
                continue
            if (
                name in self._business_tool_names
                and name not in visible_business_names
            ):
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
