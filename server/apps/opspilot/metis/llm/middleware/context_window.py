"""Fit each DeepAgent model request into the model's derived working window."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.agent.tool_execution_planner import is_context_size_error
from apps.opspilot.metis.llm.chain.context_usage import CONTEXT_USAGE_EVENT, summarize_llm_context_usage
from apps.opspilot.metis.llm.chain.prepare_llm_context import prepare_messages_for_llm

_RETRY_LOG_TEMPLATE = "event=llm_context_window_retry failed_stage=model_call error_type=%s"


class ContextWindowMiddleware(AgentMiddleware):
    """Trim, compact, and drop old tool results before every model call.

    Provider context-window errors retry once after a forced compact.
    """

    def __init__(self, *, graph_request: Any, isolated_llm: Any = None) -> None:
        super().__init__()
        self._graph_request = graph_request
        self._isolated_llm = isolated_llm

    async def _fit(self, request: ModelRequest, *, force_compact: bool = False) -> ModelRequest:
        messages = await prepare_messages_for_llm(
            list(getattr(request, "messages", None) or []),
            request=self._graph_request,
            isolated_llm=self._isolated_llm,
            tools=getattr(request, "tools", None),
            force_compact=force_compact,
        )
        return request.override(messages=messages)

    async def _emit_usage(self, fitted: ModelRequest) -> None:
        model_name = str(getattr(self._graph_request, "model", "") or "gpt-4o")
        payload = summarize_llm_context_usage(
            list(getattr(fitted, "messages", None) or []),
            request=self._graph_request,
            tools=getattr(fitted, "tools", None),
            model_name=model_name,
        )
        if payload is None:
            return
        try:
            await adispatch_custom_event(CONTEXT_USAGE_EVENT, payload)
        except Exception as exc:
            logger.debug(
                "event=llm_context_usage_emit_skipped failed_stage=model_call error_type=%s",
                type(exc).__name__,
            )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        async def _handler(fitted: ModelRequest) -> ModelResponse | AIMessage:
            return handler(fitted)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.awrap_model_call(request, _handler))
        raise NotImplementedError("ContextWindowMiddleware.wrap_model_call cannot run inside an event loop; " "use awrap_model_call")

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse | AIMessage]],
    ) -> ModelResponse | AIMessage:
        fitted = await self._fit(request)
        await self._emit_usage(fitted)
        try:
            return await handler(fitted)
        except Exception as exc:
            if not is_context_size_error(exc):
                raise
            logger.warning(_RETRY_LOG_TEMPLATE, type(exc).__name__)
            fitted = await self._fit(request, force_compact=True)
            await self._emit_usage(fitted)
            return await handler(fitted)
