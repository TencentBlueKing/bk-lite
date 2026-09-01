"""Classify LLM provider failures so logs can tell connection vs auth vs other errors."""

from __future__ import annotations

from typing import Any, Mapping

# Stable codes for logs / RUN_ERROR. Keep ASCII so ops can grep without encoding issues.
LLM_ERROR_UNREACHABLE = "LLM_UNREACHABLE"
LLM_ERROR_TIMEOUT = "LLM_TIMEOUT"
LLM_ERROR_AUTH = "LLM_AUTH"
LLM_ERROR_RATE_LIMIT = "LLM_RATE_LIMIT"
LLM_ERROR_BAD_REQUEST = "LLM_BAD_REQUEST"
LLM_ERROR_BLOCKED = "LLM_BLOCKED"
LLM_ERROR_EMPTY = "LLM_EMPTY_RESPONSE"
LLM_ERROR_UNKNOWN = "LLM_ERROR"

_USER_MESSAGES = {
    LLM_ERROR_UNREACHABLE: "无法连接大模型服务，请检查 API 地址、网络连通性或白名单",
    LLM_ERROR_TIMEOUT: "大模型响应超时，请稍后重试或检查模型服务负载",
    LLM_ERROR_AUTH: "大模型鉴权失败，请检查 API Key / Token",
    LLM_ERROR_RATE_LIMIT: "大模型触发限流，请稍后重试",
    LLM_ERROR_BAD_REQUEST: "大模型请求被拒绝，请检查模型名与请求参数",
    LLM_ERROR_BLOCKED: "请求被网关或 WAF 拦截，不是 API Key 无效。请确认网关允许服务端发起的流式 POST",
    LLM_ERROR_EMPTY: "大模型已连通但返回空内容",
    LLM_ERROR_UNKNOWN: "大模型调用失败",
}

_UNREACHABLE_NEEDLES = (
    "connection refused",
    "connection reset",
    "connect error",
    "connecttimeout",
    "connection timed out",
    "failed to establish a new connection",
    "name or service not known",
    "nodename nor servname provided",
    "no such host",
    "getaddrinfo failed",
    "network is unreachable",
    "temporary failure in name resolution",
    "all connection attempts failed",
    "remote end closed connection",
    "server disconnected",
    "errno 111",
    "errno 61",
    "errno 110",
    "apiconnectionerror",
    "connecterror",
    "httperror",
)

_TIMEOUT_NEEDLES = (
    "timed out",
    "timeout",
    "readtimeout",
    "writetimeout",
    "deadline exceeded",
)

_AUTH_NEEDLES = (
    "unauthorized",
    "authentication",
    "invalid api key",
    "incorrect api key",
    "invalid_api_key",
    "permission denied",
    "access denied",
    "401",
    "403",
)

# WAF/CDN often returns HTTP 403 with this body; that is not an invalid API key.
_GATEWAY_BLOCKED_NEEDLES = (
    "your request was blocked",
    "you have been blocked",
    "sorry, you have been blocked",
    "blocked by cloudflare",
    "attention required",
)

_RATE_LIMIT_NEEDLES = (
    "rate limit",
    "too many requests",
    "429",
    "quota exceeded",
    "insufficient_quota",
)

_BAD_REQUEST_NEEDLES = (
    "bad request",
    "invalid request",
    "model_not_found",
    "does not exist",
    "not found",
    "400",
    "404",
    "unsupported",
)


def _exc_text(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    parts = [type(exc).__name__, str(exc or "")]
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        parts.append(type(cause).__name__)
        parts.append(str(cause or ""))
    context = getattr(exc, "__context__", None)
    if isinstance(context, BaseException) and context is not cause:
        parts.append(type(context).__name__)
        parts.append(str(context or ""))
    return " ".join(parts).casefold()


def _status_code(exc: BaseException | None) -> int | None:
    if exc is None:
        return None
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def classify_llm_error(exc: BaseException | None) -> dict[str, Any]:
    """Return a structured classification for an LLM call failure."""
    text = _exc_text(exc)
    status = _status_code(exc)
    type_name = type(exc).__name__ if exc is not None else "None"

    if any(n in text for n in _GATEWAY_BLOCKED_NEEDLES):
        code = LLM_ERROR_BLOCKED
    elif status in {401, 403} or any(n in text for n in _AUTH_NEEDLES):
        code = LLM_ERROR_AUTH
    elif status == 429 or any(n in text for n in _RATE_LIMIT_NEEDLES):
        code = LLM_ERROR_RATE_LIMIT
    elif status in {400, 404, 422} or any(n in text for n in _BAD_REQUEST_NEEDLES):
        # Prefer unreachable over bad_request when connection keywords dominate.
        if any(n in text for n in _UNREACHABLE_NEEDLES):
            code = LLM_ERROR_UNREACHABLE
        else:
            code = LLM_ERROR_BAD_REQUEST
    elif any(n in text for n in _UNREACHABLE_NEEDLES) or type_name in {
        "APIConnectionError",
        "ConnectError",
        "ConnectTimeout",
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
    }:
        code = LLM_ERROR_UNREACHABLE
    elif any(n in text for n in _TIMEOUT_NEEDLES) or type_name in {
        "APITimeoutError",
        "ReadTimeout",
        "WriteTimeout",
        "TimeoutError",
        "Timeout",
    }:
        code = LLM_ERROR_TIMEOUT
    else:
        code = LLM_ERROR_UNKNOWN

    return {
        "code": code,
        "category": code,
        "unreachable": code == LLM_ERROR_UNREACHABLE,
        "user_message": _USER_MESSAGES[code],
        "error_type": type_name,
        "status_code": status,
        "detail": str(exc or "")[:800],
    }


def summarize_llm_endpoint(request: Any = None, *, model: str = "", api_base: str = "") -> dict[str, str]:
    """Safe endpoint summary for logs (no API keys)."""
    resolved_model = model or str(getattr(request, "model", "") or "")
    resolved_base = api_base or str(getattr(request, "openai_api_base", "") or "")
    protocol = str(getattr(request, "protocol_type", "") or "") if request is not None else ""
    vendor = str(getattr(request, "vendor_type", "") or "") if request is not None else ""
    return {
        "model": resolved_model,
        "api_base": resolved_base,
        "protocol_type": protocol,
        "vendor_type": vendor,
    }


def format_llm_failure_log(
    *,
    stage: str,
    classification: Mapping[str, Any],
    endpoint: Mapping[str, str] | None = None,
) -> str:
    """One-line ops-friendly log for grepping ``LLM 调用失败`` / ``LLM_UNREACHABLE``."""
    ep = endpoint or {}
    return (
        f"LLM 调用失败 stage={stage} category={classification.get('code')} "
        f"unreachable={bool(classification.get('unreachable'))} "
        f"model={ep.get('model') or '-'} api_base={ep.get('api_base') or '-'} "
        f"protocol={ep.get('protocol_type') or '-'} vendor={ep.get('vendor_type') or '-'} "
        f"error_type={classification.get('error_type')} "
        f"status={classification.get('status_code')} detail={classification.get('detail')}"
    )


def format_llm_empty_response_log(
    *,
    stage: str,
    endpoint: Mapping[str, str] | None = None,
    extra: str = "",
) -> str:
    ep = endpoint or {}
    suffix = f" {extra}" if extra else ""
    return (
        f"LLM 调用完成但返回空内容 stage={stage} category={LLM_ERROR_EMPTY} "
        f"model={ep.get('model') or '-'} api_base={ep.get('api_base') or '-'} "
        f"protocol={ep.get('protocol_type') or '-'} vendor={ep.get('vendor_type') or '-'}{suffix}"
    )
