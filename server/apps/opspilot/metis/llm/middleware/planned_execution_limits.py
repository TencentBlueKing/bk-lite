"""分步 DeepAgent 执行的模型次数 / token 预算限制。

次数限制为失控兜底；token 预算（请求或环境变量配置时）为主控。
触顶注入带标记的中文说明，由外层决定是否向用户询问继续。
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState, hook_config
from langchain_core.callbacks import dispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.channels.untracked_value import UntrackedValue
from typing_extensions import Annotated, NotRequired

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.metis.llm.common.token_usage import TokenUsageAccumulator

LimitKind = Literal["model_calls", "token_budget"]

LIMIT_MARKER_MODEL_CALLS = "[OPSPILOT_LIMIT:model_calls]"
LIMIT_MARKER_TOKEN_BUDGET = "[OPSPILOT_LIMIT:token_budget]"
_LIMIT_MARKERS = (LIMIT_MARKER_MODEL_CALLS, LIMIT_MARKER_TOKEN_BUDGET)

_RUN_MODEL_CALL_LIMIT_ENV = "OPSPILOT_DEEPAGENT_RUN_MODEL_CALL_LIMIT"
_DEFAULT_RUN_MODEL_CALL_LIMIT = 10
_MAX_TOKENS_BUDGET_ENV = "OPSPILOT_DEEPAGENT_MAX_TOKENS_BUDGET"
_DEFAULT_MAX_TOKENS_BUDGET = 0
_MAX_CONTINUE_PER_STEP = 3
_SOFT_WRAP_UP_HINT = "【预算提示】累计 token 已接近上限，请尽快基于已有证据收尾，" "避免继续大量工具调用；证据不足时只补最关键的一次查询。"


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
        self._extra_run_allowance = 0
        self._extra_token_allowance = 0
        self._soft_warned = False
        self.continue_count = 0
        self.enforce_limits = True

    @property
    def effective_run_limit(self) -> int:
        return self.run_limit + self._extra_run_allowance

    @property
    def effective_token_budget(self) -> int:
        if self.token_budget <= 0:
            return 0
        return self.token_budget + self._extra_token_allowance

    def grant_continue(self, kind: LimitKind) -> bool:
        """用户选择继续后放宽额度；超过每步续跑上限则拒绝。"""
        if self.continue_count >= _MAX_CONTINUE_PER_STEP:
            return False
        self.continue_count += 1
        if kind == "token_budget":
            # 再给半份原预算，至少 1 万 token，避免立刻再次触顶。
            grant = max(10_000, self.token_budget // 2) if self.token_budget > 0 else 10_000
            self._extra_token_allowance += grant
        else:
            self._extra_run_allowance += self.run_limit
        return True

    def reset_step_continues(self) -> None:
        self.continue_count = 0

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
) -> bool:
    """向用户确认是否放宽限制继续当前步骤；超时默认结束。"""
    from apps.opspilot.metis.llm.chain.report_renderers.k8s import build_a2ui_report_contract
    from apps.opspilot.utils.user_choice import wait_for_choice

    configurable = (config or {}).get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict):
        configurable = {}
    execution_id = str(configurable.get("execution_id") or "") or str(int(time.time() * 1000))
    # 与 request_user_choice / submit_choice 的 skill_test 兜底保持一致：
    # 技能本地测试不写 WorkFlowTaskResult，node_id=deep_agent 会导致提交 404。
    node_id = str(configurable.get("node_id") or "skill_test")
    choice_id = str(uuid.uuid4())[:8]

    if kind == "token_budget":
        title = f"步骤「{step_objective}」已达 token 预算上限，是否继续执行？"
    else:
        title = f"步骤「{step_objective}」已达模型调用次数上限，是否继续执行？"

    options_data = [
        {"key": "continue", "label": "继续", "description": "放宽限制后从中断处继续", "recommended": True},
        {"key": "stop", "label": "结束本步骤", "description": "保留已有证据并进入后续步骤/总结", "recommended": False},
    ]
    choice_request_data = {
        "execution_id": execution_id,
        "node_id": node_id,
        "choice_id": choice_id,
        "a2ui": build_a2ui_report_contract(
            component="user-choice",
            event_name="user_choice_request",
            actions=[{"key": "submit_choice", "label": "提交选择"}],
        ),
        "title": title,
        "description": "继续会再放宽一档额度；结束则基于已有结果进入后续步骤或总结。",
        "options": options_data,
        "multiple": False,
        "min_select": 1,
        "max_select": 1,
        "timeout_seconds": 120,
        "default_keys": ["stop"],
        "display_hint": "auto",
    }
    try:
        dispatch_custom_event("user_choice_request", choice_request_data, config=config)
    except Exception as exc:
        logger.debug("限制续跑选择事件派发跳过: %s", exc)

    result = await wait_for_choice(
        execution_id=execution_id,
        node_id=node_id,
        choice_id=choice_id,
        options=options_data,
        default_keys=["stop"],
        timeout_seconds=120,
        poll_interval=1.0,
        trigger_type="interactive",
    )
    selected = result.get("selected") or []
    return "continue" in selected
