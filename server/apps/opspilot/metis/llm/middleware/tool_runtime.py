from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_exception_info
from apps.opspilot.metis.llm.agent.tool_execution_planner import (
    _DEFAULT_PLANNED_AI_TEXT_CHARS,
    _DEFAULT_PLANNED_TOOL_RESULT_CHARS,
    compact_planned_execution_messages,
)
from apps.opspilot.metis.llm.common.tool_failure import POLICY_RESULT_MARKER, is_non_replanable_tool_failure

# 兼容旧导入路径（实现见 planned_execution_limits）。
from apps.opspilot.metis.llm.middleware.planned_execution_limits import (  # noqa: F401
    get_planned_execution_max_tokens_budget,
    get_planned_execution_run_model_call_limit,
)

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

    def _tool_is_visible(self, name: str) -> bool:
        if not name or name in self._hidden_tools:
            return False
        visible_business_names = {_tool_name(tool) for tool in self._active_tools if _tool_name(tool)}
        if self._activator is not None:
            visible_business_names.add(_tool_name(self._activator))
        if self.include_always_visible:
            visible_business_names |= self._always_visible_tools
        if not self._allow_unregistered_tools and name not in visible_business_names:
            return False
        if name in self._business_tool_names and name not in visible_business_names:
            return False
        return True

    def _deny_invisible_tool(self, request: Any) -> ToolMessage | None:
        call = getattr(request, "tool_call", None) or {}
        name = str(call.get("name") or "")
        if self._tool_is_visible(name):
            return None
        if self._tool_is_visible("execute"):
            next_hint = "不要改调未计划工具或扫文件。" "直接 execute 本步技能脚本；若脚本已返回，把结果告诉用户并结束。"
        else:
            next_hint = "只调用本步骤可见的业务工具。" "不要改调其他工具，不要用文件工具绕过。" "已有结构化结果（含空列表）时直接回答并结束本步，不要因此重规划。"
        return ToolMessage(
            content=f"{POLICY_RESULT_MARKER} 工具 {name or '(unknown)'} 当前不可用。{next_hint}",
            tool_call_id=str(call.get("id") or ""),
            name=name or "unknown",
            status="error",
        )

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

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_invisible_tool(request)
        if denied is not None:
            return denied
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_invisible_tool(request)
        if denied is not None:
            return denied
        return await handler(request)


_SKILL_RESULT_MARKER = "[OPSPILOT_SKILL_RESULT]"
_SKILL_STOP_MARKER = "[OPSPILOT_SKILL_STOP]"
_SKILL_SCRIPT_RE = re.compile(r"/skills/[^/\s]+/scripts/[^/\s]+\.py")
_SKILL_SUCCESS_HINTS = ("已成功返回数据", "已成功结束且无匹配数据")
_SKILL_FAIL_HINTS = ("脚本失败", "被沙箱拒绝")
_SKILL_STOP_HINT = f"{_SKILL_STOP_MARKER} 不要再调用工具。把上一轮脚本的结果或错误原样告诉用户并结束。"

SkillHistoryKind = Literal["ok", "fail", "fs_probe", "other"]


def inspect_skill_execution_history(messages: Sequence[Any] | None) -> tuple[int, int, SkillHistoryKind | None]:
    """统计技能脚本 execute 成败，以及最后一次工具调用类型。"""
    script_ok = 0
    script_fail = 0
    last_kind: SkillHistoryKind | None = None
    for message in messages or []:
        if not isinstance(message, ToolMessage):
            continue
        name = str(getattr(message, "name", "") or "")
        content = str(message.content or "")
        if name in PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS:
            last_kind = "fs_probe"
            continue
        if name != "execute":
            last_kind = "other"
            continue
        if _SKILL_RESULT_MARKER in content:
            if any(hint in content for hint in _SKILL_SUCCESS_HINTS):
                script_ok += 1
                last_kind = "ok"
            elif any(hint in content for hint in _SKILL_FAIL_HINTS):
                script_fail += 1
                last_kind = "fail"
            else:
                script_fail += 1
                last_kind = "fail"
            continue
        if "当前不可用" in content or "禁止 read_file" in content or "不要扫" in content:
            last_kind = "fs_probe"
            continue
        last_kind = "other"
    return script_ok, script_fail, last_kind


def _request_messages(request: Any) -> list[Any]:
    messages = getattr(request, "messages", None)
    if messages:
        return list(messages)
    state = getattr(request, "state", None)
    if isinstance(state, dict):
        return list(state.get("messages") or [])
    if state is not None:
        nested = getattr(state, "messages", None)
        if nested:
            return list(nested)
    return []


class SkillExecutionGuardMiddleware(AgentMiddleware):
    """纯技能步：拦住扫包工具，脚本成功或失败探文件后收掉工具，避免读到 10 次上限。"""

    def __init__(self, *, enabled: bool = False, max_script_attempts: int = 2) -> None:
        super().__init__()
        self.enabled = enabled
        self.max_script_attempts = max(1, int(max_script_attempts))

    def _has_unrecoverable_script_failure(self, messages: Sequence[Any] | None) -> bool:
        for message in messages or []:
            if not isinstance(message, ToolMessage):
                continue
            if str(getattr(message, "name", "") or "") != "execute":
                continue
            status = str(getattr(message, "status", "") or "")
            if is_non_replanable_tool_failure(message.content, status):
                return True
        return False

    def _terminal(
        self,
        script_ok: int,
        script_fail: int,
        last_kind: SkillHistoryKind | None,
        messages: Sequence[Any] | None = None,
    ) -> bool:
        if script_ok >= 1:
            return True
        if self._has_unrecoverable_script_failure(messages):
            return True
        if script_fail >= self.max_script_attempts:
            return True
        return script_fail >= 1 and last_kind == "fs_probe"

    def _filter_request(self, request: ModelRequest) -> ModelRequest:
        if not self.enabled:
            return request
        messages = _request_messages(request)
        script_ok, script_fail, last_kind = inspect_skill_execution_history(messages)
        if not self._terminal(script_ok, script_fail, last_kind, messages):
            return request
        if not any(_SKILL_STOP_MARKER in str(getattr(message, "content", "") or "") for message in messages):
            messages = messages + [HumanMessage(content=_SKILL_STOP_HINT)]
        return request.override(messages=messages, tools=[])

    def _deny_tool(self, request: Any) -> ToolMessage | None:
        if not self.enabled:
            return None
        call = getattr(request, "tool_call", None) or {}
        name = str(call.get("name") or "")
        call_id = str(call.get("id") or "")
        messages = _request_messages(request)
        script_ok, script_fail, last_kind = inspect_skill_execution_history(messages)
        terminal = self._terminal(script_ok, script_fail, last_kind, messages)

        if name in PLANNED_EXECUTION_ALWAYS_VISIBLE_FS_TOOLS:
            return ToolMessage(
                content=(f"{_SKILL_RESULT_MARKER} 禁止 read_file/ls/grep 扫技能包。" "直接 execute `/skills/<包名>/scripts/...`；" "若脚本已失败，把错误原样告诉用户并结束，不要再读文件。"),
                tool_call_id=call_id,
                name=name or "unknown",
                status="error",
            )

        if name != "execute":
            if terminal:
                return ToolMessage(
                    content=_SKILL_STOP_HINT,
                    tool_call_id=call_id,
                    name=name or "unknown",
                    status="error",
                )
            return None

        command = str((call.get("args") or {}).get("command") or "")
        is_script = bool(_SKILL_SCRIPT_RE.search(command))
        if terminal:
            return ToolMessage(
                content=_SKILL_STOP_HINT,
                tool_call_id=call_id,
                name="execute",
                status="error",
            )
        if script_ok >= 1 or script_fail >= 1:
            if not is_script:
                return ToolMessage(
                    content=(f"{_SKILL_RESULT_MARKER} 不要再用 cat/ls/grep/echo 探测。" "最多再 execute 一次 `/skills/<包名>/scripts/...`；" "否则把上一轮错误原样告诉用户并结束。"),
                    tool_call_id=call_id,
                    name="execute",
                    status="error",
                )
        return None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        return handler(self._filter_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse | AIMessage]],
    ) -> ModelResponse | AIMessage:
        return await handler(self._filter_request(request))

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_tool(request)
        if denied is not None:
            return denied
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        denied = self._deny_tool(request)
        if denied is not None:
            return denied
        return await handler(request)


class ToolExceptionAsResultMiddleware(AgentMiddleware):
    """工具抛异常时写成 ToolMessage，保证 AG-UI 能收到 TOOL_CALL_RESULT。

    kubeconfig 解析失败等会在工具内 raise；若不拦截，ainvoke 直接崩掉，前端只能把
    挂起的 TOOL_CALL_START 收成「已完成但未收到结果」，看起来像成功。
    """

    def _error_message(self, request: Any, exc: BaseException) -> ToolMessage:
        call = getattr(request, "tool_call", None) or {}
        name = str(call.get("name") or "unknown")
        call_id = str(call.get("id") or "")
        logger.error(
            "event=agent_tool_failed failed_stage=tool_call error_type=%s tool_name=%s",
            type(exc).__name__,
            name,
            exc_info=safe_exception_info(exc),
        )
        text = str(exc).strip() or f"{type(exc).__name__}: tool execution failed"
        return ToolMessage(
            content=text[:2000],
            tool_call_id=call_id,
            name=name,
            status="error",
        )

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return handler(request)
        except Exception as exc:
            return self._error_message(request, exc)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        try:
            return await handler(request)
        except Exception as exc:
            return self._error_message(request, exc)


class ToolResultCompactionMiddleware(AgentMiddleware):
    """分步执行步内：每次模型调用前截断过长工具结果，上限随输入工作预算放大。"""

    def __init__(
        self,
        *,
        max_tool_chars: int = _DEFAULT_PLANNED_TOOL_RESULT_CHARS,
        max_ai_chars: int = _DEFAULT_PLANNED_AI_TEXT_CHARS,
    ) -> None:
        super().__init__()
        self._max_tool_chars = max_tool_chars
        self._max_ai_chars = max_ai_chars

    def _compact_request(self, request: ModelRequest) -> ModelRequest:
        messages = list(getattr(request, "messages", None) or [])
        compacted = compact_planned_execution_messages(
            messages,
            max_tool_chars=self._max_tool_chars,
            max_ai_chars=self._max_ai_chars,
        )
        return request.override(messages=compacted)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        return handler(self._compact_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[
            [ModelRequest],
            Awaitable[ModelResponse | AIMessage],
        ],
    ) -> ModelResponse | AIMessage:
        return await handler(self._compact_request(request))
