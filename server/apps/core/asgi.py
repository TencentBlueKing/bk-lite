"""补齐 Django 4.2 响应发送异常时的请求资源清理。"""

import asyncio

import django
from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIHandler

from apps.core.logger import logger, safe_exception_info


class ResponseCleanupASGIHandler(ASGIHandler):
    async def send_response(self, response, send):
        try:
            await super().send_response(response, send)
        except BaseException:
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
                "event=asgi_cleanup_failed status_code=%s failed_stage=response_close error_type=%s",
                response.status_code,
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )


def get_asgi_application():
    """保持 Django 工厂的初始化顺序，只替换当前应用的 handler。"""
    django.setup(set_prefix=False)
    return ResponseCleanupASGIHandler()
