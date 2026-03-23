"""
达梦数据库连接中间件。

解决 ASGI 模式下达梦同步驱动导致的并发阻塞问题。

问题：
1. 达梦驱动是同步阻塞的，在 ASGI 模式下 Django 将 ORM 操作放到线程池执行
2. 多个请求共享数据库连接时，可能出现连接级别的锁竞争
3. 当线程都在等待数据库响应时，新请求无法处理

解决方案：
1. 在每个请求开始前关闭旧连接，确保获取新连接
2. 在每个请求结束后关闭连接，避免连接被其他请求复用
3. 配合 CONN_MAX_AGE=0 使用，确保不复用连接
"""

import logging
import os
import threading

from django.db import connections

logger = logging.getLogger(__name__)

# 只在达梦数据库环境下启用
_IS_DAMENG = os.getenv("DB_ENGINE", "").lower() == "dameng"

# 调试开关
_DEBUG_CONNECTION = os.getenv("DEBUG_DAMENG_CONNECTION", "0") == "1"


class DamengConnectionMiddleware:
    """
    达梦数据库连接管理中间件。

    确保每个请求使用独立的数据库连接，避免并发阻塞。
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._local = threading.local()

    def __call__(self, request):
        if _IS_DAMENG:
            self._ensure_fresh_connection()

        try:
            response = self.get_response(request)
        finally:
            if _IS_DAMENG:
                self._close_connections()

        return response

    def _ensure_fresh_connection(self):
        """
        确保当前线程使用新的数据库连接。

        这会关闭当前线程持有的所有数据库连接，
        下次 ORM 操作时会自动创建新连接。
        """
        thread_id = threading.current_thread().ident

        for alias in connections:
            conn = connections[alias]
            if conn.connection is not None:
                if _DEBUG_CONNECTION:
                    logger.info(f"[DAMENG_CONN] Thread {thread_id}: Closing old connection for alias '{alias}'")
                try:
                    conn.close()
                except Exception as e:
                    if _DEBUG_CONNECTION:
                        logger.warning(f"[DAMENG_CONN] Thread {thread_id}: Error closing connection: {e}")

    def _close_connections(self):
        """
        关闭当前线程的所有数据库连接。

        这在请求结束后执行，确保连接不会被其他请求复用。
        """
        thread_id = threading.current_thread().ident

        for alias in connections:
            conn = connections[alias]
            if conn.connection is not None:
                if _DEBUG_CONNECTION:
                    logger.info(f"[DAMENG_CONN] Thread {thread_id}: Closing connection after request for alias '{alias}'")
                try:
                    conn.close()
                except Exception as e:
                    if _DEBUG_CONNECTION:
                        logger.warning(f"[DAMENG_CONN] Thread {thread_id}: Error closing connection: {e}")
