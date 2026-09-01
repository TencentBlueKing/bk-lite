"""Derive per-call working budgets from an LLM model's true context window."""

from __future__ import annotations

from dataclasses import dataclass

from apps.opspilot.models import LLMModel

DEFAULT_CONTEXT_WINDOW_TOKENS = 200_000
MIN_CONTEXT_WINDOW_TOKENS = 8_000
MAX_CONTEXT_WINDOW_TOKENS = 2_000_000
DEFAULT_CHAT_SCENE_OUTPUT_TOKENS = 4000

_SAFETY_RATIO = 5
_OUTPUT_CAP_RATIO = 10
_COMPACTION_RATIO = 75
_KNOWLEDGE_RATIO = 15
_BUILD_CHUNK_RATIO = 15
_SINGLE_MESSAGE_RATIO = 20
_MIN_SAFETY_TOKENS = 256


@dataclass(frozen=True)
class LLMWorkingBudget:
    window_tokens: int
    safety_tokens: int
    output_reserve_tokens: int
    input_working_tokens: int
    compaction_threshold_tokens: int
    knowledge_inject_tokens: int
    build_chunk_tokens: int
    single_message_tokens: int


def _percent(value: int, ratio: int) -> int:
    return value * ratio // 100


def derive_llm_working_budget(window_tokens: int, *, scene_output_default: int) -> LLMWorkingBudget:
    window = int(window_tokens)
    safety = max(_MIN_SAFETY_TOKENS, _percent(window, _SAFETY_RATIO))
    output_cap = _percent(window, _OUTPUT_CAP_RATIO)
    output_reserve = min(max(int(scene_output_default), 0), output_cap)
    input_working = max(window - output_reserve - safety, 0)
    return LLMWorkingBudget(
        window_tokens=window,
        safety_tokens=safety,
        output_reserve_tokens=output_reserve,
        input_working_tokens=input_working,
        compaction_threshold_tokens=_percent(input_working, _COMPACTION_RATIO),
        knowledge_inject_tokens=_percent(input_working, _KNOWLEDGE_RATIO),
        build_chunk_tokens=_percent(input_working, _BUILD_CHUNK_RATIO),
        single_message_tokens=_percent(input_working, _SINGLE_MESSAGE_RATIO),
    )


CONTEXT_WINDOW_RANGE_ERROR = "上下文窗口须在 8000～2000000 token 之间"


def normalize_context_window_tokens(value) -> int:
    if value is None:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    return int(value)


def parse_context_window_tokens(value=None) -> int:
    if value is None or value == "":
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    try:
        tokens = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(CONTEXT_WINDOW_RANGE_ERROR) from error
    if tokens < MIN_CONTEXT_WINDOW_TOKENS or tokens > MAX_CONTEXT_WINDOW_TOKENS:
        raise ValueError(CONTEXT_WINDOW_RANGE_ERROR)
    return tokens


def window_tokens_for_model_id(llm_model_id) -> int:
    if not llm_model_id:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    value = LLMModel.objects.filter(pk=llm_model_id).values_list("context_window_tokens", flat=True).first()
    return normalize_context_window_tokens(value)


def window_tokens_for_model(llm_model) -> int:
    if llm_model is None:
        return DEFAULT_CONTEXT_WINDOW_TOKENS
    return normalize_context_window_tokens(getattr(llm_model, "context_window_tokens", None))


def working_budget_for_model(llm_model, *, scene_output_default: int) -> LLMWorkingBudget:
    return derive_llm_working_budget(
        window_tokens_for_model(llm_model),
        scene_output_default=scene_output_default,
    )


def working_budget_for_model_id(llm_model_id, *, scene_output_default: int) -> LLMWorkingBudget:
    return derive_llm_working_budget(
        window_tokens_for_model_id(llm_model_id),
        scene_output_default=scene_output_default,
    )
