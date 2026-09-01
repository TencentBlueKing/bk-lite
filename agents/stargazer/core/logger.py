"""Stargazer 统一日志入口。

采集运行时与插件适配层统一从本模块导入 logger，
底层使用 Sanic 框架 logger，避免各文件自行 getLogger。
"""

from __future__ import annotations

from sanic.log import logger


class SafeLogException(RuntimeError):
    """仅供日志 traceback 渲染使用的受控异常代理。"""


def safe_log_value(value, *, max_length: int = 160) -> str:
    """返回有界单行日志副本，不改变业务层原值。"""

    return str(value or "").replace("\r", "\\r").replace("\n", "\\n")[:max_length]


def safe_exception_info(error: BaseException):
    """保留原 traceback 帧，同时用稳定正文替换可能敏感的异常消息。"""

    safe_error = SafeLogException(type(error).__name__)
    return SafeLogException, safe_error, error.__traceback__


__all__ = ["logger", "safe_exception_info", "safe_log_value"]
