"""Django ORM 旁路线程连接清理。

``close_old_connections`` 只作用于调用它的线程（connections 为 thread-local）。
在 ThreadPoolExecutor / ``sync_to_async(thread_sensitive=False)`` /
asyncio 默认 executor 里访问 ORM 时，必须在**真正建连的那个线程**上清理，
否则 idle 连接会永久驻留，最终打满 PostgreSQL ``max_connections``。
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from django.db import close_old_connections

from apps.core.logger import opspilot_logger as logger

F = TypeVar("F", bound=Callable[..., Any])


def run_with_db_cleanup(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """在当前线程执行 func，前后关闭过期/不可用的 Django DB 连接。"""
    close_old_connections()
    try:
        return func(*args, **kwargs)
    finally:
        close_old_connections()


def with_db_cleanup(func: F) -> F:
    """装饰器：保证被装饰函数无论成功失败都会清理本线程 Django 连接。"""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return run_with_db_cleanup(func, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def wrap_langchain_tool(tool: Any) -> Any:
    """包装 LangChain StructuredTool 的同步 ``func``，使每次工具调用后清理连接。"""
    original = getattr(tool, "func", None)
    # 用 ``is True``：MagicMock 等对任意属性返回真值对象，不能直接当 bool 用。
    if original is None or getattr(original, "_db_cleanup_wrapped", False) is True:
        return tool

    wrapped = with_db_cleanup(original)
    wrapped._db_cleanup_wrapped = True  # type: ignore[attr-defined]
    try:
        tool.func = wrapped
    except Exception:
        # 部分 StructuredTool 实现可能禁止直接赋值，退化为不影响调用方
        logger.warning(
            "wrap_langchain_tool: 无法替换 tool.func，跳过连接清理包装: tool=%r",
            getattr(tool, "name", type(tool).__name__),
            exc_info=True,
        )
    return tool
