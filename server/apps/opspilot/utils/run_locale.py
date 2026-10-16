# -*- coding: utf-8 -*-
"""当前对话轮次的页面语言。工具结果在返回前读取它。"""
import contextvars

_run_locale: contextvars.ContextVar[str] = contextvars.ContextVar("opspilot_run_locale", default="en")


def set_run_locale(locale: str | None) -> contextvars.Token:
    """写入本轮页面语言，返回 token。调用方必须在 finally 里 reset。"""
    return _run_locale.set((locale or "en").strip() or "en")


def reset_run_locale(token: contextvars.Token) -> None:
    _run_locale.reset(token)


def get_run_locale() -> str:
    return _run_locale.get() or "en"
