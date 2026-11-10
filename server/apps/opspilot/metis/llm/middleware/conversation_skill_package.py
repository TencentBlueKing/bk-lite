"""prepare_conversation_skill_package 校验通过后结束本轮。失败时不终止，由工具返回原因。"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain_core.messages import AIMessage

from apps.opspilot.services.conversation_skill_package import (
    PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL,
    prepare_conversation_skill_package,
    publish_conversation_skill_package_choice,
)


def _configurable(runtime: Any) -> dict[str, Any]:
    config = getattr(runtime, "config", None)
    if not isinstance(config, dict):
        return {}
    configurable = config.get("configurable")
    return dict(configurable) if isinstance(configurable, dict) else {}


def _tool_call_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_call_args(call: Any) -> dict[str, Any]:
    if isinstance(call, dict):
        args = call.get("args") or {}
    else:
        args = getattr(call, "args", None) or {}
    return dict(args) if isinstance(args, dict) else {}


def _tool_call_id(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "")
    return str(getattr(call, "id", "") or "")


def _package_calls(message: Any) -> list[Any]:
    calls = getattr(message, "tool_calls", None) or []
    return [call for call in calls if _tool_call_name(call) == PREPARE_CONVERSATION_SKILL_PACKAGE_TOOL]


class ConversationSkillPackageMiddleware(AgentMiddleware):
    """成稿校验通过才结束本轮并出示确认卡。"""

    @hook_config(can_jump_to=["end"])
    def after_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        prepared = self._prepare(state, runtime)
        return self._finish(prepared, state, runtime)

    @hook_config(can_jump_to=["end"])
    async def aafter_model(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        prepared = await sync_to_async(self._prepare, thread_sensitive=True)(state, runtime)
        return self._finish(prepared, state, runtime)

    def _prepare(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages:
            return None
        calls = _package_calls(messages[-1])
        if not calls:
            return None
        args = _tool_call_args(calls[0])
        configurable = _configurable(runtime)
        graph_request = configurable.get("graph_request")
        config = getattr(runtime, "config", None)
        return prepare_conversation_skill_package(
            name=str(args.get("name") or ""),
            description=str(args.get("description") or ""),
            triggers=args.get("triggers"),
            skill_markdown=str(args.get("skill_markdown") or ""),
            graph_request=graph_request,
            config=config if isinstance(config, dict) else {"configurable": configurable},
        )

    def _finish(self, prepared: dict[str, Any] | None, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        if not prepared or not prepared.get("ok"):
            return None
        messages = list(state.get("messages") or [])
        call = _package_calls(messages[-1])[0]
        configurable = _configurable(runtime)
        config = getattr(runtime, "config", None)
        _visible, tool_message = publish_conversation_skill_package_choice(
            prepared,
            graph_request=configurable.get("graph_request"),
            config=config if isinstance(config, dict) else {"configurable": configurable},
            messages=messages[:-1],
            tool_call_id=_tool_call_id(call),
        )
        return {
            "jump_to": "end",
            "messages": [tool_message, AIMessage(content=prepared["text"])],
        }
