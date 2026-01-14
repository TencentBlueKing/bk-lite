"""
请求耗时记录中间件
记录每个请求的处理时间，并可选记录慢请求
"""
import logging
import time

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("app")


class RequestTimingMiddleware(MiddlewareMixin):
    """记录请求处理耗时的中间件"""

    # 慢请求阈值（毫秒），超过此阈值会记录WARNING日志
    SLOW_REQUEST_THRESHOLD_MS = getattr(settings, "SLOW_REQUEST_THRESHOLD_MS", 1000)

    # 是否在响应头中添加耗时信息（开发环境建议开启）
    ADD_TIMING_HEADER = getattr(settings, "ADD_REQUEST_TIMING_HEADER", settings.DEBUG)

    # 排除路径（不记录日志的路径前缀）
    EXCLUDE_PATHS = [
        "/static/",
        "/media/",
        "/favicon.ico",
        "/health/",
        "/ping/",
    ]

    def process_request(self, request):
        """记录请求开始时间"""
        request._start_time = time.time()
        return None

    def process_response(self, request, response):
        """计算并记录请求耗时"""
        if not hasattr(request, "_start_time"):
            return response

        # 计算耗时（毫秒）
        elapsed_time = (time.time() - request._start_time) * 1000

        # 检查是否需要排除
        if self._should_exclude(request.path):
            return response

        # 添加响应头（可选）
        if self.ADD_TIMING_HEADER:
            response["X-Request-Time"] = f"{elapsed_time:.2f}ms"

        # 记录日志
        self._log_request(request, response, elapsed_time)

        return response

    def _should_exclude(self, path):
        """判断是否应该排除此路径"""
        return any(path.startswith(prefix) for prefix in self.EXCLUDE_PATHS)

    def _log_request(self, request, response, elapsed_time_ms):
        """记录请求日志"""
        method = request.method
        path = request.path
        status_code = response.status_code

        # 构建日志消息
        log_message = f"Request: {method} {path} - {status_code} - {elapsed_time_ms:.2f}ms"

        # 根据耗时和状态码选择日志级别
        if elapsed_time_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(f"Slow {log_message} (threshold: {self.SLOW_REQUEST_THRESHOLD_MS}ms)")
        elif status_code >= 500:
            logger.error(log_message)
        elif status_code >= 400:
            logger.warning(log_message)
        else:
            logger.info(log_message)
