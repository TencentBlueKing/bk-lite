# -*- coding: utf-8 -*-
"""把工具返回里已收录的中文换成当前对话语言。"""
from types import SimpleNamespace
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from apps.opspilot.utils.returned_messages import localize_embedded_text
from apps.opspilot.utils.run_locale import get_run_locale


def _locale_from_request(request: Any) -> str:
    runtime = getattr(request, "runtime", None)
    config = getattr(runtime, "config", None)
    configurable = {}
    if isinstance(config, dict):
        raw = config.get("configurable")
        if isinstance(raw, dict):
            configurable = raw
    graph_request = configurable.get("graph_request")
    locale = getattr(graph_request, "locale", None) or configurable.get("locale") or get_run_locale()
    return str(locale or "en")


def _localize_result(result: Any, locale: str) -> Any:
    loader = SimpleNamespace(default_lang=locale)
    if isinstance(result, ToolMessage):
        content = result.content
        if isinstance(content, str):
            translated = localize_embedded_text(content, loader)
            if translated != content:
                return result.model_copy(update={"content": translated})
        return result
    if isinstance(result, str):
        return localize_embedded_text(result, loader)
    return result


class ToolResultLocaleMiddleware(AgentMiddleware):
    """工具成功或失败返回后，按本轮 locale 替换已收录的中文。"""

    def wrap_tool_call(self, request: Any, handler):
        result = handler(request)
        return _localize_result(result, _locale_from_request(request))

    async def awrap_tool_call(self, request: Any, handler):
        result = await handler(request)
        return _localize_result(result, _locale_from_request(request))
