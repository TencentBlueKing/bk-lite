"""插件异常日志：输出有界、可检索且不包含异常正文的调用链。"""

from __future__ import annotations

import re
import threading
import traceback
from typing import Any, Mapping

_MAX_CALL_CHAIN_FRAMES = 12
_SAFE_TOKEN = re.compile(r"[^A-Za-z0-9_.:/@-]+")


class PluginExceptionSampler:
    """一个 Run 共享的异常样本额度；兼容插件在线程中报告异常。"""

    def __init__(self, limit: int = 3) -> None:
        self._remaining = max(0, int(limit))
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True


def should_log_plugin_exception(params: Mapping[str, Any]) -> bool:
    sampler = params.get("_plugin_exception_sampler")
    if isinstance(sampler, PluginExceptionSampler):
        return sampler.take()
    return bool(params.get("_log_plugin_call_chain"))


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


def _call_chain(error: BaseException) -> str:
    frames = []
    seen_errors = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen_errors:
        seen_errors.add(id(current))
        frames.extend(traceback.extract_tb(current.__traceback__))
        current = current.__cause__ or current.__context__
    if not frames:
        return "-"
    return ">".join(f"{_short_filename(frame.filename)}:{frame.lineno}:{_safe_token(frame.name)}" for frame in frames[-_MAX_CALL_CHAIN_FRAMES:])


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
    """记录插件异常上下文；刻意不记录 ``str(error)`` 或源码内容。"""

    log_method = getattr(logger, level, logger.error)
    log_method(
        "event=plugin_exception task_id=%s plugin_ref=%s model_id=%s " "plugin_name=%s target=%s error_type=%s call_chain=%s",
        _safe_token(task_id),
        _safe_token(plugin_ref),
        _safe_token(model_id),
        _safe_token(plugin_name),
        _safe_token(target, default="logical"),
        _safe_token(type(error).__name__),
        _call_chain(error),
    )
