# -*- coding: utf-8 -*-
"""当前对话轮次的页面语言。工具结果在返回前读取它。"""
import contextvars

_run_locale: contextvars.ContextVar[str] = contextvars.ContextVar("opspilot_run_locale", default="en")


def set_run_locale(locale: str | None) -> None:
    _run_locale.set((locale or "en").strip() or "en")


def get_run_locale() -> str:
    return _run_locale.get() or "en"
