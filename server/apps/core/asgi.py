"""补齐 Django 4.2 响应发送异常时的请求资源清理。"""

import asyncio
import contextlib
from contextvars import ContextVar

import django
from asgiref.sync import sync_to_async
from django.core.handlers.asgi import ASGIHandler

from apps.core.db_diagnostics import current_trace, install_diagnostics, trace_request
from apps.core.logger import logger, safe_exception_info, safe_log_value

# 只在当前请求任务内可见。handler 实例被并发请求共用，不能把 receive 存在 self 上。
_asgi_receive: ContextVar = ContextVar("bklite_asgi_receive", default=None)


async def _watch_client_disconnect(receive, disconnect: asyncio.Event) -> None:
    """流式响应期间再读一条 ASGI 消息。只认断开，避免把下一次请求读走。"""
    try:
        message = await receive()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        # receive 失败按断开处理，流可以结束。正文可能含传输细节，只留类型。
        trace = current_trace.get()
        logger.warning(
            "event=asgi_disconnect_watch_failed request_id=%s failed_stage=receive error_type=%s",
            trace.request_id if trace is not None else "-",
            type(error).__name__,
            exc_info=safe_exception_info(error),
        )
        disconnect.set()
        return
    if message.get("type") == "http.disconnect":
        disconnect.set()


async def _stop_on_disconnect(iterator, disconnect: asyncio.Event):
    """客户端断开后停止异步流。uvicorn 的 send() 在断开后直接返回，不会打断生成器。"""
    pending_next = None
    pending_wait = None
    try:
        while True:
            if disconnect.is_set():
                return
            pending_next = asyncio.ensure_future(iterator.__anext__())
            pending_wait = asyncio.ensure_future(disconnect.wait())
            done, _pending = await asyncio.wait(
                {pending_next, pending_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if pending_next not in done:
                pending_next.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_next
                return
            pending_wait.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending_wait
            try:
                part = pending_next.result()
            except StopAsyncIteration:
                return
            pending_next = None
            pending_wait = None
            yield part
    finally:
        for task in (pending_next, pending_wait):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(RuntimeError):
                await aclose()


async def _finish_disconnect_watch(watch_task: asyncio.Task | None) -> None:
    if watch_task is None:
        return
    if not watch_task.done():
        watch_task.cancel()
    while not watch_task.done():
        try:
            await asyncio.shield(watch_task)
        except asyncio.CancelledError:
            continue
    if watch_task.cancelled():
        return
    error = watch_task.exception()
    if error is None:
        return
    trace = current_trace.get()
    logger.error(
        "event=asgi_cleanup_failed request_id=%s status_code=%s failed_stage=disconnect_watch error_type=%s",
        trace.request_id if trace is not None else "-",
        "-",
        type(error).__name__,
        exc_info=safe_exception_info(error),
    )


class ResponseCleanupASGIHandler(ASGIHandler):
    async def __call__(self, scope, receive, send):
        # 在父类退出 ThreadSensitiveContext 后观测；不额外调度 ORM 或创建连接。
        with trace_request(scope):
            await super().__call__(scope, receive, send)

    async def handle(self, scope, receive, send):
        token = _asgi_receive.set(receive)
        try:
            await super().handle(scope, receive, send)
        finally:
            _asgi_receive.reset(token)

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

        watch_task = None
        try:
            receive = _asgi_receive.get()
            # 只包异步流。同步文件下载保持原路径，短请求也不再读下一条 ASGI 消息。
            if response.streaming and getattr(response, "is_async", False) and receive is not None:
                disconnect = asyncio.Event()
                response.streaming_content = _stop_on_disconnect(response._iterator, disconnect)
                watch_task = asyncio.create_task(
                    _watch_client_disconnect(receive, disconnect),
                    name="asgi-client-disconnect",
                )
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
            await _finish_disconnect_watch(watch_task)
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
