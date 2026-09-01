"""插件异常日志：输出有界、可检索且不包含异常正文的源码调用上下文。"""

from __future__ import annotations

import re
import threading
import traceback
from typing import Any, Mapping

_MAX_CALL_CHAIN_FRAMES = 12
_MAX_SOURCE_LINE_LENGTH = 300
_MAX_ERROR_MESSAGE_LENGTH = 1000
_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9_.:/@-]+")
_SENSITIVE_ERROR_MESSAGE = re.compile(r"(?i)\b(?:password|passwd|pwd|token|secret|community|auth_?key|priv_?key|cookie|credential)\b")
_SENSITIVE_SOURCE_DOUBLE_QUOTED = re.compile(
    r'(?i)(?:[rubf]*)"[^"\n]*(?:password|passwd|pwd|token|community|secret|auth_?key|priv_?key|cookie|credential)[^"\n]*"'
)
_SENSITIVE_SOURCE_SINGLE_QUOTED = re.compile(
    r"(?i)(?:[rubf]*)'[^'\n]*(?:password|passwd|pwd|token|community|secret|auth_?key|priv_?key|cookie|credential)[^'\n]*'"
)


class PluginExceptionLogBudget:
    """一个 Collection Run 共享的插件异常详情采样预算。"""

    def __init__(self, *, limit: int) -> None:
        if limit < 0:
            raise ValueError("limit must not be negative")
        self._remaining = int(limit)
        self._lock = threading.Lock()

    def claim(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True


def should_log_plugin_exception(params: Mapping[str, Any]) -> bool:
    if not bool(params.get("_log_plugin_call_chain")):
        return False
    budget = params.get("_plugin_exception_log_budget")
    if isinstance(budget, PluginExceptionLogBudget):
        return budget.claim()
    return True


def _safe_token(value: Any, *, default: str = "-", max_length: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return _SAFE_TOKEN.sub("_", text)[:max_length] or default


def _short_filename(filename: str) -> str:
    normalized = str(filename or "").replace("\\", "/")
    for marker in ("/agents/stargazer/", "/app/"):
        if marker in normalized:
            return normalized.split(marker, 1)[1]
    parts = [part for part in normalized.split("/") if part]
    return "/".join(parts[-4:]) or "unknown"


def _safe_error_message(error: BaseException) -> str:
    text = str(error or "").strip()
    if not text:
        return "-"
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    text = "".join(char if char.isprintable() else "?" for char in text)
    if _SENSITIVE_ERROR_MESSAGE.search(text):
        return "[REDACTED]"
    return text[:_MAX_ERROR_MESSAGE_LENGTH]


def _traceback_frames(error: BaseException) -> list[traceback.FrameSummary]:
    frames = []
    seen_errors = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen_errors:
        seen_errors.add(id(current))
        frames.extend(traceback.extract_tb(current.__traceback__))
        current = current.__cause__ or current.__context__
    return frames[-_MAX_CALL_CHAIN_FRAMES:]


def _call_chain(frames: list[traceback.FrameSummary]) -> str:
    if not frames:
        return "-"
    return ">".join(f"{_short_filename(frame.filename)}:{frame.lineno}:{_safe_token(frame.name)}" for frame in frames)


def _source_context(frames: list[traceback.FrameSummary]) -> str:
    """格式化 traceback 的源码行；不包含异常正文、局部变量或运行时参数值。"""
    if not frames:
        return "-"
    lines = []
    for frame in frames:
        lines.append(f'  File "{_short_filename(frame.filename)}", line {frame.lineno}, ' f"in {_safe_token(frame.name)}")
        source_line = str(frame.line or "<source unavailable>").strip()
        source_line = "".join(char if char.isprintable() else "?" for char in source_line)
        source_line = _SENSITIVE_SOURCE_DOUBLE_QUOTED.sub('"[REDACTED]"', source_line)
        source_line = _SENSITIVE_SOURCE_SINGLE_QUOTED.sub("'[REDACTED]'", source_line)
        lines.append(f"    {source_line[:_MAX_SOURCE_LINE_LENGTH]}")
    return "\n".join(lines)


def log_plugin_exception(
    logger,
    *,
    error: BaseException,
    task_id: Any,
    plugin_ref: Any,
    model_id: Any,
    plugin_name: Any,
    target: Any,
    level: str = "error",
) -> None:
    """记录插件异常的安全正文和源码调用上下文，不记录局部变量或凭据。"""

    log_method = getattr(logger, level, logger.error)
    frames = _traceback_frames(error)
    log_method(
        "event=plugin_exception task_id=%s plugin_ref=%s model_id=%s "
        "plugin_name=%s target=%s error_type=%s error_message=%s call_chain=%s\n"
        "source_context=\n%s",
        _safe_token(task_id),
        _safe_token(plugin_ref),
        _safe_token(model_id),
        _safe_token(plugin_name),
        _safe_token(target, default="logical"),
        _safe_token(type(error).__name__),
        _safe_error_message(error),
        _call_chain(frames),
        _source_context(frames),
    )
