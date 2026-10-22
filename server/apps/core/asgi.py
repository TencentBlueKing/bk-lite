"""补齐 Django 4.2 响应发送异常时的请求资源清理。"""

import asyncio

import django
from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIHandler

from apps.core.db_diagnostics import current_trace, install_diagnostics, trace_request
from apps.core.logger import logger, safe_exception_info, safe_log_value


class ResponseCleanupASGIHandler(ASGIHandler):
    async def __call__(self, scope, receive, send):
        # 在父类退出 ThreadSensitiveContext 后观测；不额外调度 ORM 或创建连接。
        with trace_request(scope):
            await super().__call__(scope, receive, send)

    async def get_response_async(self, request):
        trace = current_trace.get()
        if trace is not None:
            request.request_id = trace.request_id
            trace.phase("application")
        try:
            return await super().get_response_async(request)
        finally:
            if trace is not None and request.resolver_match is not None:
                trace.route = safe_log_value(request.resolver_match.route)

    async def send_response(self, response, send):
        trace = current_trace.get()
        if trace is not None:
            trace.status_code = response.status_code
            trace.phase("send_response")
            original_send = send

            async def send(message):
                await original_send(message)
                if message["type"] == "http.response.body" and not message.get("more_body", False):
                    trace.phase("response_close")

        try:
            await super().send_response(response, send)
        except BaseException:
            if trace is not None:
                trace.cleanup_fallback = True
            # 此时仍处于 ASGIHandler.__call__ 的 ThreadSensitiveContext 内。
            # 清理排在原同步线程上；即使取消发生在已有 close 中，也等待它完成。
            cleanup = asyncio.create_task(sync_to_async(self._close_response, thread_sensitive=True)(response))
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    # 重复取消不能让请求先退出、丢失原线程上下文；清理后原样上抛。
                    continue
            cleanup.result()
            raise
        finally:
            if trace is not None:
                trace.response_closed = response.closed

    @staticmethod
    def _close_response(response):
        # 必须在线程内检查：先前被取消的 close 可能仍在该线程执行。
        if response.closed:
            return
        try:
            response.close()
        except Exception as error:
            # 保留发送异常/取消的所有权；仅记录独立的清理故障，不泄露异常正文。
            logger.error(
                "event=asgi_cleanup_failed request_id=%s status_code=%s failed_stage=response_close error_type=%s",
                current_trace.get().request_id if current_trace.get() is not None else "-",
                response.status_code,
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )


def get_asgi_application():
    """保持 Django 工厂的初始化顺序，只替换当前应用的 handler。"""
    django.setup(set_prefix=False)
    install_diagnostics()
    return ResponseCleanupASGIHandler()
