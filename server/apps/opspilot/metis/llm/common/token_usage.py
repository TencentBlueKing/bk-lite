from dataclasses import dataclass, field
from typing import Any, Mapping


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _token_count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if count < 0:
        return None
    return count


def _extract_usage_source(message: Any) -> tuple[Any, str, str]:
    usage_metadata = getattr(message, "usage_metadata", None)
    if usage_metadata:
        return usage_metadata, "input_tokens", "output_tokens"

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = _get_value(response_metadata, "token_usage")
    if token_usage:
        return token_usage, "prompt_tokens", "completion_tokens"
    return None, "", ""


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reported: bool = False


@dataclass(frozen=True)
class TokenUsageCall:
    call_index: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reported: bool = False
    visible_tools: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_index": self.call_index,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reported": self.reported,
            "visible_tool_count": len(self.visible_tools),
            "visible_tools": list(self.visible_tools),
        }


def extract_token_usage(message: Any) -> TokenUsage:
    source, prompt_key, completion_key = _extract_usage_source(message)
    if source is None:
        return TokenUsage()

    prompt_tokens = _token_count(_get_value(source, prompt_key)) or 0
    completion_tokens = _token_count(_get_value(source, completion_key)) or 0
    calculated_total = prompt_tokens + completion_tokens
    reported_total = _token_count(_get_value(source, "total_tokens"))
    total_tokens = reported_total if reported_total not in (None, 0) else calculated_total
    return TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens, reported=True)


@dataclass
class TokenUsageAccumulator:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    missing_usage_calls: int = 0
    calls: list[TokenUsageCall] = field(default_factory=list)
    middleware_tracking: bool = False
    _seen_run_ids: set[str] = field(default_factory=set)

    def add(
        self,
        run_id: Any,
        message: Any,
        *,
        visible_tools: list[str] | tuple[str, ...] | None = None,
    ) -> tuple[bool, bool]:
        normalized_run_id = str(run_id).strip() if run_id is not None else ""
        if normalized_run_id and normalized_run_id in self._seen_run_ids:
            return False, False
        if normalized_run_id:
            self._seen_run_ids.add(normalized_run_id)

        usage = extract_token_usage(message)
        normalized_tools = tuple(dict.fromkeys(str(name) for name in (visible_tools or []) if name))
        self.calls.append(
            TokenUsageCall(
                call_index=len(self.calls) + 1,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                reported=usage.reported,
                visible_tools=normalized_tools,
            )
        )
        if not usage.reported:
            self.missing_usage_calls += 1
            return True, False

        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        return True, True

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def as_openai_usage(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }

    def as_call_details(self) -> list[dict[str, Any]]:
        return [call.as_dict() for call in self.calls]
