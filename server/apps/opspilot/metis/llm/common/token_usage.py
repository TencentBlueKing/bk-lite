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


def _first_token_count(source: Any, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        count = _token_count(_get_value(source, key))
        if count is not None:
            return count
    return None


_PROMPT_KEYS = ("input_tokens", "prompt_tokens", "prompt_token_count", "input_token_count")
_COMPLETION_KEYS = ("output_tokens", "completion_tokens", "completion_token_count", "output_token_count")
_TOTAL_KEYS = ("total_tokens", "total_token_count")


def _extract_usage_source(message: Any) -> Any:
    """Locate provider usage payload on an AIMessage / chunk.

    Prefer LangChain ``usage_metadata``; fall back to OpenAI-style
    ``response_metadata.token_usage`` / ``response_metadata.usage``.
    Some OpenAI-compatible gateways (e.g. MiniMax) only populate the latter
    when streaming without ``stream_options.include_usage``, or put OpenAI
    key names inside ``usage_metadata``.
    """
    usage_metadata = getattr(message, "usage_metadata", None)
    if usage_metadata and (_first_token_count(usage_metadata, _PROMPT_KEYS + _COMPLETION_KEYS + _TOTAL_KEYS) is not None):
        return usage_metadata

    response_metadata = getattr(message, "response_metadata", None) or {}
    for key in ("token_usage", "usage"):
        token_usage = _get_value(response_metadata, key)
        if token_usage and (_first_token_count(token_usage, _PROMPT_KEYS + _COMPLETION_KEYS + _TOTAL_KEYS) is not None):
            return token_usage
    # usage_metadata 存在但全空时仍返回它,便于调用方标记「有字段但无有效用量」
    if usage_metadata:
        return usage_metadata
    return None


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
    source = _extract_usage_source(message)
    if source is None:
        return TokenUsage()

    prompt_tokens = _first_token_count(source, _PROMPT_KEYS)
    completion_tokens = _first_token_count(source, _COMPLETION_KEYS)
    reported_total = _first_token_count(source, _TOTAL_KEYS)

    # 有 usage 容器但三种计数都缺 → 视为未上报
    if prompt_tokens is None and completion_tokens is None and reported_total is None:
        return TokenUsage()

    prompt_tokens = prompt_tokens or 0
    completion_tokens = completion_tokens or 0
    calculated_total = prompt_tokens + completion_tokens
    total_tokens = reported_total if reported_total not in (None, 0) else calculated_total
    # LangChain/兼容网关常塞来全 0 的 usage_metadata(空 usage 对象或流式终包丢失),
    # 不能当成「已上报 0」,否则 AGUI 日志永远是 0 且不再走兜底。
    if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        reported=True,
    )


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
