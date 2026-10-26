"""分步 DeepAgent 执行的模型次数 / token 预算限制。

次数限制为失控兜底；token 预算（请求或环境变量配置时）为主控。
触顶注入带标记的中文说明，由外层决定是否向用户询问继续。
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.channels.untracked_value import UntrackedValue
from typing_extensions import Annotated, NotRequired

from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator
from apps.opspilot.metis.llm.middleware.terminal_user_choice import finalize_user_choice
from apps.opspilot.utils.pending_question import KIND_LIMIT_CONTINUE

LimitKind = Literal["model_calls", "token_budget"]

LIMIT_MARKER_MODEL_CALLS = "[OPSPILOT_LIMIT:model_calls]"
LIMIT_MARKER_TOKEN_BUDGET = "[OPSPILOT_LIMIT:token_budget]"
_LIMIT_MARKERS = (LIMIT_MARKER_MODEL_CALLS, LIMIT_MARKER_TOKEN_BUDGET)

_RUN_MODEL_CALL_LIMIT_ENV = "OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT"
_DEFAULT_RUN_MODEL_CALL_LIMIT = 10
_MAX_TOKENS_BUDGET_ENV = "OPSPILOT_DEEPAGENT_MAX_TOKENS_BUDGET"
_DEFAULT_MAX_TOKENS_BUDGET = 0
_SOFT_WRAP_UP_HINT = "【预算提示】累计 token 已接近上限，请尽快基于已有证据收尾，" "避免继续大量工具调用；证据不足时只补最关键的一次查询。"


def resolve_planned_execution_run_model_call_limit(graph_request: Any) -> int:
    """智能体配置优先；0 或非法时回退环境变量。"""
    raw = getattr(graph_request, "run_model_call_limit", 0) or 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return get_planned_execution_run_model_call_limit()


def get_planned_execution_run_model_call_limit() -> int:
    """分步执行每步（单次 ainvoke）模型调用上限；默认 10，非法值回退默认。"""
    raw = os.getenv(_RUN_MODEL_CALL_LIMIT_ENV)
    if raw is None or not str(raw).strip():
        return _DEFAULT_RUN_MODEL_CALL_LIMIT
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return _DEFAULT_RUN_MODEL_CALL_LIMIT
    if value <= 0:
        return _DEFAULT_RUN_MODEL_CALL_LIMIT
    return value


def get_planned_execution_max_tokens_budget() -> int:
    """分步执行累计 token 预算；默认 0=不限制，非法值回退默认。"""
    raw = os.getenv(_MAX_TOKENS_BUDGET_ENV)
    if raw is None or not str(raw).strip():
        return _DEFAULT_MAX_TOKENS_BUDGET
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return _DEFAULT_MAX_TOKENS_BUDGET
    if value < 0:
        return _DEFAULT_MAX_TOKENS_BUDGET
    return value


def resolve_planned_execution_token_budget(graph_request: Any) -> int:
    """请求字段优先，其次环境变量；0 表示不限制。"""
    req = int(getattr(graph_request, "max_tokens_budget", 0) or 0)
    if req > 0:
        return req
    return get_planned_execution_max_tokens_budget()


def resolve_planned_execution_soft_budget_ratio(graph_request: Any) -> float:
    raw = getattr(graph_request, "soft_budget_ratio", 0.8)
    try:
        ratio = float(raw)
    except (TypeError, ValueError):
        return 0.8
    if ratio <= 0 or ratio > 1:
        return 0.8
    return ratio


def build_limit_exceeded_message(
    kind: LimitKind,
    *,
    used: int,
    limit: int,
) -> str:
    if kind == "token_budget":
        return f"当前任务累计 token 已达预算上限（{used}/{limit}），本步骤暂时停止。" f"{LIMIT_MARKER_TOKEN_BUDGET}"
    return f"当前步骤模型调用次数已达上限（{used}/{limit}），本步骤暂时停止。" f"{LIMIT_MARKER_MODEL_CALLS}"


def detect_limit_kind(messages: list[Any] | None) -> LimitKind | None:
    for message in reversed(messages or []):
        if not isinstance(message, AIMessage):
            continue
        text = str(message.content or "")
        if LIMIT_MARKER_TOKEN_BUDGET in text:
            return "token_budget"
        if LIMIT_MARKER_MODEL_CALLS in text:
            return "model_calls"
    return None


def is_limit_stop_ai_message(message: Any) -> bool:
    """触顶后注入的终止说明，不应进入步间摘要或已有结论。"""
    if not isinstance(message, AIMessage):
        return False
    if getattr(message, "tool_calls", None):
        return False
    text = str(message.content or "")
    return any(marker in text for marker in _LIMIT_MARKERS)


def filter_messages_without_limit_stop(messages: list[Any] | None) -> list[Any]:
    return [message for message in (messages or []) if not is_limit_stop_ai_message(message)]


_EXHAUSTED_LIMIT_CLAIM_RE = re.compile(
    r"(?:但|并且|而且)?\s*"
    r"(?:本会话|当前步骤|当前任务|这一步)?\s*"
    r"(?:累计\s*)?"
    r"(?:"
    r"(?:模型调用次数|工具调用次数|调用次数|次数|token\s*预算)\s*(?:已达上限|已达到上限|用尽)"
    r"|(?:已达|达到)\s*(?:模型调用次数|工具调用次数|调用次数|次数|token\s*预算)\s*上限"
    r"|token\s*已达预算上限"
    r")"
    r"(?:\s*[（(][^）)]*[）)])?"
    r"|本步骤暂时停止"
    r"|\[OPSPILOT_LIMIT:[^\]]+\]",
    re.IGNORECASE,
)
_LIMIT_MENU_LINE_RE = re.compile(r"^(?:是否继续执行？|[12][\.、．]\s*(?:继续|结束本步骤)|回复后会开启新一轮.*)$")
_STEP_TITLE_BEFORE_CONTINUE_RE = re.compile(r"步骤「[^」]*」\s*[，,]?\s*(?=是否继续执行？)")
_UNFINISHED_BECAUSE_LIMIT_RE = re.compile(r"[，,]\s*这一步未能执行[。.]?")

LIMIT_RESUME_NOTE = "【次数已重置】上一轮因调用次数或 token 预算暂停已经解除，本轮从 0 重新计数。" "历史中的「次数已达上限」「次数用尽」「暂时停止」不得作为本轮停止条件，未完成的查询继续调用工具。"


def scrub_exhausted_limit_claims(text: str) -> str:
    """去掉历史里「次数已用尽」的断言，保留工具结论。续跑时不得再把它当成停止条件。"""
    body = str(text or "")
    if not body.strip():
        return ""
    for marker in _LIMIT_MARKERS:
        body = body.replace(marker, "")
    body = _EXHAUSTED_LIMIT_CLAIM_RE.sub("", body)
    body = _UNFINISHED_BECAUSE_LIMIT_RE.sub("", body)
    body = _STEP_TITLE_BEFORE_CONTINUE_RE.sub("", body)
    body = body.replace("是否继续执行？", "")
    kept: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if _LIMIT_MENU_LINE_RE.match(stripped):
            continue
        if stripped in {"是否继续执行？", "这一步未能执行。", "这一步未能执行"}:
            continue
        kept.append(line)
    body = "\n".join(kept)
    body = re.sub(r"[，,]{2,}", "，", body)
    body = re.sub(r"。{2,}", "。", body)
    body = re.sub(r"\s*，\s*。", "。", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def scrub_limit_markers_from_summary(text: str) -> str:
    """去掉上限标记与「暂时停止」句，保留结构化 carry-over 与工具结论。"""
    body = str(text or "").strip()
    if not body:
        return ""
    for marker in _LIMIT_MARKERS:
        body = body.replace(marker, "")
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and "暂时停止" in stripped and not stripped.startswith("【"):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    while "暂时停止" in body:
        start = body.find("暂时停止")
        sentence_start = max(body.rfind("。", 0, start), body.rfind("\n", 0, start)) + 1
        sentence_end = body.find("。", start)
        if sentence_end < 0:
            body = (body[:sentence_start] + body[start + len("暂时停止") :]).strip()
            break
        body = (body[:sentence_start] + body[sentence_end + 1 :]).strip()
    return body.strip()


class PlannedExecutionLimitState(AgentState):
    run_model_call_count: NotRequired[Annotated[int, UntrackedValue]]


class PlannedExecutionLimitMiddleware(AgentMiddleware):
    """每步模型调用次数兜底 + 可选累计 token 预算主控。"""

    state_schema = PlannedExecutionLimitState

    def __init__(
        self,
        *,
        run_limit: int,
        token_budget: int = 0,
        soft_budget_ratio: float = 0.8,
        accumulator: TokenUsageAccumulator | None = None,
    ) -> None:
        super().__init__()
        self.run_limit = max(1, int(run_limit))
        self.token_budget = max(0, int(token_budget or 0))
        self.soft_budget_ratio = soft_budget_ratio
        self._accumulator = accumulator
        self._soft_warned = False
        self.enforce_limits = True

    @property
    def effective_run_limit(self) -> int:
        return self.run_limit

    @property
    def effective_token_budget(self) -> int:
        if self.token_budget <= 0:
            return 0
        return self.token_budget

    def _used_tokens(self) -> int:
        if not isinstance(self._accumulator, TokenUsageAccumulator):
            return 0
        return int(self._accumulator.total_tokens or 0)

    def _token_budget_exceeded(self) -> bool:
        budget = self.effective_token_budget
        return budget > 0 and self._used_tokens() >= budget

    def _soft_budget_reached(self) -> bool:
        budget = self.effective_token_budget
        if budget <= 0 or self.soft_budget_ratio >= 1.0:
            return False
        return self._used_tokens() >= int(budget * self.soft_budget_ratio)

    def _check_hard_limit(self, state: PlannedExecutionLimitState) -> dict[str, Any] | None:
        if not self.enforce_limits:
            return None
        run_count = int(state.get("run_model_call_count", 0) or 0)
        if self._token_budget_exceeded():
            budget = self.effective_token_budget
            return {
                "jump_to": "end",
                "messages": [
                    AIMessage(
                        content=build_limit_exceeded_message(
                            "token_budget",
                            used=self._used_tokens(),
                            limit=budget,
                        )
                    )
                ],
            }
        if run_count >= self.effective_run_limit:
            return {
                "jump_to": "end",
                "messages": [
                    AIMessage(
                        content=build_limit_exceeded_message(
                            "model_calls",
                            used=run_count,
                            limit=self.effective_run_limit,
                        )
                    )
                ],
            }
        return None

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: PlannedExecutionLimitState, runtime: Any) -> dict[str, Any] | None:
        hard = self._check_hard_limit(state)
        if hard is not None:
            return hard
        if not self.enforce_limits:
            return None
        if not self._soft_warned and self._soft_budget_reached():
            self._soft_warned = True
            return {"messages": [HumanMessage(content=_SOFT_WRAP_UP_HINT)]}
        return None

    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state: PlannedExecutionLimitState, runtime: Any) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state: PlannedExecutionLimitState, runtime: Any) -> dict[str, Any] | None:
        return {"run_model_call_count": int(state.get("run_model_call_count", 0) or 0) + 1}

    async def aafter_model(self, state: PlannedExecutionLimitState, runtime: Any) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse | AIMessage],
    ) -> ModelResponse | AIMessage:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse | AIMessage]],
    ) -> ModelResponse | AIMessage:
        return await handler(request)


async def ask_limit_continue(
    *,
    kind: LimitKind,
    step_objective: str,
    config: dict[str, Any] | None,
    messages: list[Any] | None = None,
    summary: str = "",
) -> tuple[str, Any]:
    """超预算时发出继续/结束卡片并结束本轮。额度随下一轮新 run 重置。"""
    if kind == "token_budget":
        title = f"步骤「{step_objective}」已达 token 预算上限，是否继续执行？"
    else:
        title = f"步骤「{step_objective}」已达模型调用次数上限，是否继续执行？"
    conclusion = str(summary or "").strip() or "已保留当前步骤已经拿到的结果。"
    question = f"{title}\n\n已有结论：{conclusion}"
    return finalize_user_choice(
        question=question,
        question_type="single_select",
        options=["继续", "结束本步骤"],
        config=config,
        messages=list(messages or []),
        tool_call_id="",
        kind=KIND_LIMIT_CONTINUE,
        description="回复后会开启新一轮，并带着已有结果继续。",
    )
