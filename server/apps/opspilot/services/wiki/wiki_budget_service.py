"""System-level Wiki query limits and per-material LLM safety guards."""

from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, field

from apps.opspilot.services.llm_context_budget import DEFAULT_CONTEXT_WINDOW_TOKENS, derive_llm_working_budget

_DEFAULTS = {
    "WIKI_QA_MAX_LLM_CALLS": 2,
    "WIKI_QA_MAX_KNOWLEDGE_TOKENS": 8000,
    "WIKI_QA_MAX_OUTPUT_TOKENS": 4000,
    "WIKI_BUILD_MAX_LLM_CALLS_PER_MATERIAL": 64,
    "WIKI_BUILD_MAX_TOTAL_TOKENS_PER_MATERIAL": 60000,
}


class WikiBudgetConfigurationError(RuntimeError):
    pass


class WikiBudgetExceeded(RuntimeError):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class WikiBudgetConfig:
    qa_max_llm_calls: int
    qa_max_knowledge_tokens: int
    qa_max_output_tokens: int
    build_max_llm_calls_per_material: int
    build_max_total_tokens_per_material: int

    def snapshot(self):
        return asdict(self)


_config_lock = threading.Lock()
_cached_config = None


def _positive_int_env(name):
    raw = os.getenv(name)
    if raw is None:
        return _DEFAULTS[name]
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise WikiBudgetConfigurationError(f"{name} 必须是正整数，当前值无法解析") from exc
    if value <= 0:
        raise WikiBudgetConfigurationError(f"{name} 必须是正整数，当前值为 {value}")
    return value


def load_wiki_budget_config(*, force_reload=False):
    global _cached_config
    with _config_lock:
        if _cached_config is not None and not force_reload:
            return _cached_config
        _cached_config = WikiBudgetConfig(
            qa_max_llm_calls=_positive_int_env("WIKI_QA_MAX_LLM_CALLS"),
            qa_max_knowledge_tokens=_positive_int_env("WIKI_QA_MAX_KNOWLEDGE_TOKENS"),
            qa_max_output_tokens=_positive_int_env("WIKI_QA_MAX_OUTPUT_TOKENS"),
            build_max_llm_calls_per_material=_positive_int_env("WIKI_BUILD_MAX_LLM_CALLS_PER_MATERIAL"),
            build_max_total_tokens_per_material=_positive_int_env("WIKI_BUILD_MAX_TOTAL_TOKENS_PER_MATERIAL"),
        )
        return _cached_config


def estimate_tokens(text):
    """Conservative dependency-free estimate suitable for a hard preflight."""

    value = str(text or "")
    if not value:
        return 0
    cjk = sum(1 for char in value if "\u3400" <= char <= "\u9fff")
    other = len(value) - cjk
    return cjk + max(1, (other + 2) // 3)


@dataclass
class LLMCallTrace:
    stage: str
    input_tokens: int
    reserved_output_tokens: int
    output_tokens: int = 0
    usage_source: str = "estimate"
    provider_usage: dict = field(default_factory=dict)

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


class LLMCallBudget:
    """Mutable request/material-scoped counter; never shared between files."""

    def __init__(
        self,
        *,
        max_calls,
        max_total_tokens,
        scope,
        config_snapshot=None,
        soft_total_tokens=None,
        max_context_tokens_per_call=None,
    ):
        self.max_calls = int(max_calls)
        self.max_total_tokens = None if max_total_tokens is None else int(max_total_tokens)
        self.soft_total_tokens = None if soft_total_tokens is None else int(soft_total_tokens)
        self.max_context_tokens_per_call = None if max_context_tokens_per_call is None else int(max_context_tokens_per_call)
        self.scope = str(scope)
        self.config_snapshot = dict(config_snapshot or {})
        self.calls = []
        self.used_tokens = 0

    @property
    def used_calls(self):
        return len(self.calls)

    @property
    def remaining_calls(self):
        return max(self.max_calls - self.used_calls, 0)

    @property
    def remaining_tokens(self):
        if self.max_total_tokens is None:
            return None
        return max(self.max_total_tokens - self.used_tokens, 0)

    @property
    def remaining_soft_tokens(self):
        if self.soft_total_tokens is None:
            return None
        return max(self.soft_total_tokens - self.used_tokens, 0)

    @property
    def soft_budget_exceeded(self):
        return self.soft_total_tokens is not None and self.used_tokens > self.soft_total_tokens

    def ensure_call(self, stage, input_text, *, output_reserve):
        input_tokens = estimate_tokens(input_text)
        output_reserve = max(int(output_reserve or 0), 0)
        if self.used_calls + 1 > self.max_calls:
            raise WikiBudgetExceeded(
                "wiki_llm_call_budget_exceeded",
                "Wiki LLM 调用次数已达到上限",
                details=self.trace(next_stage=stage, next_input_tokens=input_tokens, next_output_reserve=output_reserve),
            )
        if self.max_context_tokens_per_call is not None and input_tokens + output_reserve > self.max_context_tokens_per_call:
            raise WikiBudgetExceeded(
                "wiki_llm_context_window_exceeded",
                "单次 Wiki LLM 输入输出超过系统安全上下文上限",
                details=self.trace(
                    next_stage=stage,
                    next_input_tokens=input_tokens,
                    next_output_reserve=output_reserve,
                ),
            )
        if self.max_total_tokens is not None and self.used_tokens + input_tokens + output_reserve > self.max_total_tokens:
            raise WikiBudgetExceeded(
                "wiki_token_budget_exceeded",
                "Wiki token 预算不足以执行下一阶段",
                details=self.trace(next_stage=stage, next_input_tokens=input_tokens, next_output_reserve=output_reserve),
            )
        return LLMCallTrace(
            stage=str(stage),
            input_tokens=input_tokens,
            reserved_output_tokens=output_reserve,
        )

    def record_call(self, reservation, output_text, *, provider_usage=None):
        provider_usage = dict(provider_usage or {})
        input_tokens = provider_usage.get("prompt_tokens") or provider_usage.get("input_tokens")
        output_tokens = provider_usage.get("completion_tokens") or provider_usage.get("output_tokens")
        if isinstance(input_tokens, int) and input_tokens >= 0:
            reservation.input_tokens = input_tokens
        if isinstance(output_tokens, int) and output_tokens >= 0:
            reservation.output_tokens = output_tokens
            reservation.usage_source = "provider"
        else:
            reservation.output_tokens = estimate_tokens(output_text)
            reservation.usage_source = "estimate"
        reservation.provider_usage = provider_usage
        self.calls.append(reservation)
        self.used_tokens += reservation.total_tokens
        if self.max_total_tokens is not None and self.used_tokens > self.max_total_tokens:
            raise WikiBudgetExceeded(
                "wiki_token_budget_exceeded_after_call",
                "Provider 实际 usage 超过 Wiki token 上限",
                details=self.trace(),
            )
        return output_text

    def invoke(self, stage, prompt, invoke, *, output_reserve):
        reservation = self.ensure_call(stage, prompt, output_reserve=output_reserve)
        result = invoke()
        provider_usage = None
        output = result
        if isinstance(result, tuple) and len(result) == 2:
            output, provider_usage = result
        return self.record_call(
            reservation,
            output or "",
            provider_usage=provider_usage,
        )

    def usage_summary(self):
        """Aggregate token usage for operator-facing logs and diagnostics."""
        input_tokens = sum(int(call.input_tokens or 0) for call in self.calls)
        output_tokens = sum(int(call.output_tokens or 0) for call in self.calls)
        provider_calls = sum(1 for call in self.calls if call.usage_source == "provider")
        estimate_calls = sum(1 for call in self.calls if call.usage_source != "provider")
        stage_parts = []
        for call in self.calls:
            stage_parts.append(f"{call.stage}:in={int(call.input_tokens or 0)},out={int(call.output_tokens or 0)},src={call.usage_source}")
        return {
            "scope": self.scope,
            "used_calls": self.used_calls,
            "used_tokens": self.used_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "provider_calls": provider_calls,
            "estimate_calls": estimate_calls,
            "soft_total_tokens": self.soft_total_tokens,
            "soft_budget_exceeded": self.soft_budget_exceeded,
            "stages": "|".join(stage_parts),
        }

    def trace(self, **extra):
        payload = {
            "scope": self.scope,
            "max_calls": self.max_calls,
            "used_calls": self.used_calls,
            "remaining_calls": self.remaining_calls,
            "max_total_tokens": self.max_total_tokens,
            "soft_total_tokens": self.soft_total_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "remaining_soft_tokens": self.remaining_soft_tokens,
            "soft_budget_exceeded": self.soft_budget_exceeded,
            "max_context_tokens_per_call": self.max_context_tokens_per_call,
            "config": self.config_snapshot,
            "calls": [
                {
                    "stage": call.stage,
                    "input_tokens": call.input_tokens,
                    "output_tokens": call.output_tokens,
                    "reserved_output_tokens": call.reserved_output_tokens,
                    "usage_source": call.usage_source,
                }
                for call in self.calls
            ],
        }
        payload.update(extra)
        return payload


def new_query_call_budget():
    config = load_wiki_budget_config()
    return LLMCallBudget(
        max_calls=config.qa_max_llm_calls,
        max_total_tokens=None,
        scope="wiki_query",
        config_snapshot=config.snapshot(),
    )


def new_material_call_budget(material_id=None, *, window_tokens=None, scene_output_default=6000):
    config = load_wiki_budget_config()
    scope = "wiki_material" if material_id is None else f"wiki_material:{material_id}"
    derived = derive_llm_working_budget(
        DEFAULT_CONTEXT_WINDOW_TOKENS if window_tokens is None else int(window_tokens),
        scene_output_default=scene_output_default,
    )
    return LLMCallBudget(
        max_calls=config.build_max_llm_calls_per_material,
        max_total_tokens=None,
        soft_total_tokens=config.build_max_total_tokens_per_material,
        max_context_tokens_per_call=derived.input_working_tokens + derived.output_reserve_tokens,
        scope=scope,
        config_snapshot=config.snapshot(),
    )


__all__ = [
    "LLMCallBudget",
    "WikiBudgetConfig",
    "WikiBudgetConfigurationError",
    "WikiBudgetExceeded",
    "estimate_tokens",
    "load_wiki_budget_config",
    "new_material_call_budget",
    "new_query_call_budget",
]
