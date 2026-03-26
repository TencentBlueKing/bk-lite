import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

# ============================================================
# 达梦数据库 ASGI 补丁 - 必须在 Django application 初始化之前应用
# ============================================================
# 问题：Django ASGI 默认使用 sync_to_async(thread_sensitive=True)，
#       这会将所有同步 ORM 操作调度到同一个"主线程"执行。
#       当使用全局锁串行化数据库操作时，所有请求都会堆积在这个线程上，
#       导致系统卡死。
#
# 解决方案：Monkey-patch sync_to_async 函数，将默认的 thread_sensitive
#           从 True 改为 False，让每个 ORM 操作在线程池的独立线程中执行。
#           这样全局锁可以正确协调多线程访问。
# ============================================================
_db_engine = os.getenv("DB_ENGINE", "postgresql").lower()
if _db_engine == "dameng":
    import functools
    import logging

    from asgiref import sync as asgiref_sync

    _original_sync_to_async = asgiref_sync.sync_to_async
    _asgi_logger = logging.getLogger(__name__)

    @functools.wraps(_original_sync_to_async)
    def _patched_sync_to_async(func=None, *, thread_sensitive=False, executor=None, context=None):
        """
        Patched sync_to_async with thread_sensitive=False as default.

        This allows Django ORM operations to run in separate thread pool threads,
        enabling proper coordination with the global database lock for Dameng.

        Supports both decorator usages:
        - @sync_to_async
        - @sync_to_async(thread_sensitive=False)
        """
        return _original_sync_to_async(
            func,
            thread_sensitive=thread_sensitive,
            executor=executor,
            context=context,
        )

    asgiref_sync.sync_to_async = _patched_sync_to_async
    _asgi_logger.info("[DAMENG_ASGI] sync_to_async patched with thread_sensitive=False")

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
