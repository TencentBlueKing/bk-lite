from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        function = tool.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "")
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", "") or "")


class TokenUsageTrackingMiddleware(AgentMiddleware):
    def __init__(self, accumulator: TokenUsageAccumulator) -> None:
        super().__init__()
        self._accumulator = accumulator
        self._accumulator.middleware_tracking = True

    def _record(self, request: ModelRequest, response: ModelResponse | AIMessage) -> None:
        visible_tools = [
            name
            for tool in request.tools
            if (name := _tool_name(tool))
        ]
        messages = response.result if isinstance(response, ModelResponse) else [response]
        for message in messages:
            if isinstance(message, AIMessage):
                self._accumulator.add(
                    None,
                    message,
                    visible_tools=visible_tools,
                )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        response = handler(request)
        self._record(request, response)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[
            [ModelRequest],
            Awaitable[ModelResponse | AIMessage],
        ],
    ) -> ModelResponse | AIMessage:
        response = await handler(request)
        self._record(request, response)
        return response
