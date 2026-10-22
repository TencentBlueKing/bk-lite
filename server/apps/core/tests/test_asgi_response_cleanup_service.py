"""通过实际 ASGI 入口验证响应发送失败时的线程、连接和资源生命周期。"""

import asyncio
import io
import logging
import runpy
import sys
import threading
import time
from pathlib import Path

import pytest
from django.contrib.sessions.models import Session
from django.core.signals import request_finished
from django.db import connection, connections, models, transaction
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.urls import clear_url_caches, path
from django.utils import timezone

urlpatterns = []


class PgActivity(models.Model):
    pid = models.IntegerField(primary_key=True)

    class Meta:
        app_label = "sessions"
        managed = False
        db_table = "pg_stat_activity"


def backend_pid(driver):
    return driver.info.backend_pid if hasattr(driver, "info") else driver.get_backend_pid()


def assert_backends_gone(pids):
    deadline = time.monotonic() + 2
    while PgActivity.objects.filter(pid__in=pids).exists():
        assert time.monotonic() < deadline, "对应 PG 会话必须从 pg_stat_activity 消失"
        time.sleep(0.01)


@pytest.fixture
def application(settings, monkeypatch):
    """保留真实 handler，只隔离与请求清理无关的启动翻译预热。"""
    from apps.core.utils import loader

    settings.MIDDLEWARE = []
    settings.ROOT_URLCONF = __name__
    settings.ALLOWED_HOSTS = ["testserver"]
    monkeypatch.setattr(loader, "preload_language_cache", lambda **kwargs: None)
    monkeypatch.setenv("DB_ENGINE", "postgresql")
    clear_url_caches()
    app = runpy.run_path(str(Path(__file__).resolve().parents[3] / "asgi.py"))["application"]
    yield app
    clear_url_caches()


def scope():
    return {
        "type": "http",
        "method": "GET",
        "path": "/resource/",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1),
        "scheme": "http",
        "http_version": "1.1",
    }


async def receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def install_view(monkeypatch, view):
    monkeypatch.setattr(sys.modules[__name__], "urlpatterns", [path("resource/", view)])
    clear_url_caches()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("failure", ["normal", "send_error", "cancel"])
@pytest.mark.parametrize("response_kind", ["plain", "file", "stream"])
def test_asgi_response_releases_real_connection_and_resources(application, monkeypatch, failure, response_kind):
    if connection.vendor != "postgresql":
        pytest.skip("真实连接生命周期验证需要 PostgreSQL")
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 0)
    state = {"closed_threads": [], "finished_threads": []}
    send_error = OSError("模拟发送失败")

    def view(request):
        state["view_thread"] = threading.get_ident()
        state["request"] = request
        # 在响应生成前完成事务；发送失败不得回滚已完成的业务写入。
        with transaction.atomic():
            Session.objects.create(session_key="asgi-cleanup-test", session_data="", expire_date=timezone.now())
            state["wrapper"] = connections["default"]
            state["driver"] = connection.connection
            state["backend_pid"] = backend_pid(connection.connection)
            assert connection.in_atomic_block
            assert not connection.connection.closed
        if response_kind == "file":
            state["file"] = io.BytesIO(b"file-body")
            response = FileResponse(state["file"])
        elif response_kind == "stream":

            async def stream():
                try:
                    yield b"stream-body"
                finally:
                    state["stream_closed"] = True

            response = StreamingHttpResponse(stream())
        else:
            response = HttpResponse(b"plain-body")
        response._resource_closers.append(lambda: state["closed_threads"].append(threading.get_ident()))
        state["response"] = response
        return response

    def finished(**kwargs):
        state["finished_threads"].append(threading.get_ident())

    install_view(monkeypatch, view)
    request_finished.connect(finished, weak=False)

    async def exercise():
        sending = asyncio.Event()
        messages = []

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body":
                sending.set()
                if failure == "send_error":
                    raise send_error
                if failure == "cancel":
                    await asyncio.Future()

        task = asyncio.create_task(application(scope(), receive, send))
        try:
            await asyncio.wait_for(sending.wait(), 5)
            if failure == "cancel":
                task.cancel("请求已取消")
                with pytest.raises(asyncio.CancelledError, match="请求已取消"):
                    await task
            elif failure == "send_error":
                with pytest.raises(OSError) as caught:
                    await task
                assert caught.value is send_error
            else:
                await task
                assert messages[0]["status"] == 200
                assert b"".join(message.get("body", b"") for message in messages).endswith(b"body")
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(exercise())
        assert state["driver"].closed, "响应发送结束后，原线程的真实 PG 连接必须关闭"
        assert_backends_gone([state["backend_pid"]])
        assert state["closed_threads"] == [state["view_thread"]]
        assert state["finished_threads"] == [state["view_thread"]]
        assert state["request"]._stream.closed
        assert state["response"].closed
        if response_kind == "file":
            assert state["file"].closed
        if response_kind == "stream":
            assert state["stream_closed"]
        assert Session.objects.filter(session_key="asgi-cleanup-test").exists()
    finally:
        request_finished.disconnect(finished)
        # 失败基线也回收测试自己的连接，不能依赖线程退出/GC 掩盖遗漏。
        wrapper = state.get("wrapper")
        if wrapper is not None:
            wrapper.inc_thread_sharing()
            try:
                wrapper.close()
            finally:
                wrapper.dec_thread_sharing()


@pytest.mark.parametrize("cancel_during", ["send", "close"])
def test_repeated_cancellation_waits_for_cleanup_without_closing_twice(application, monkeypatch, cancel_during):
    started = threading.Event()
    release = threading.Event()
    state = {"close_calls": 0}

    class SlowResponse(HttpResponse):
        def close(self):
            state["close_calls"] += 1
            started.set()
            state["released"] = release.wait(5)
            super().close()

    response = SlowResponse(b"body")
    install_view(monkeypatch, lambda request: response)

    async def exercise():
        sending = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body":
                sending.set()
                if cancel_during == "send":
                    await asyncio.Future()

        task = asyncio.create_task(application(scope(), receive, send))
        try:
            await asyncio.wait_for(sending.wait(), 5)
            if cancel_during == "send":
                task.cancel("首次取消")
            for _ in range(500):
                if started.is_set() or task.done():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set(), "取消后必须进入响应清理"
            if cancel_during == "close":
                task.cancel("首次取消")
                await asyncio.sleep(0)
            task.cancel("再次取消")
            await asyncio.sleep(0.01)
            assert not task.done(), "清理完成前不能退出请求的线程上下文"
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert response.closed
            assert state == {"close_calls": 1, "released": True}
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


def test_cleanup_failure_preserves_send_error_and_logs_safely(application, monkeypatch, caplog):
    sentinel = "secret-must-not-appear-asgi-cleanup"
    close_error = RuntimeError(sentinel)
    send_error = OSError("original send failure")
    response = HttpResponse(b"body")
    install_view(monkeypatch, lambda request: response)

    def broken_receiver(**kwargs):
        raise close_error

    async def send(message):
        raise send_error

    request_finished.connect(broken_receiver, weak=False)
    try:
        with pytest.raises(OSError) as caught:
            asyncio.run(application(scope(), receive, send))
        assert caught.value is send_error
        assert response.closed
        records = [record for record in caplog.records if record.name == "app" and record.levelno >= logging.ERROR]
        assert len(records) == 1
        record = records[0]
        assert record.args
        assert "failed_stage=response_close" in record.getMessage()
        assert "error_type=RuntimeError" in record.getMessage()
        assert record.exc_info[2] is close_error.__traceback__
        assert sentinel not in logging.Formatter().format(record)
    finally:
        request_finished.disconnect(broken_receiver)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_cancelled_requests_do_not_close_other_inflight_connections(application, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("真实连接生命周期验证需要 PostgreSQL")
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 0)
    states = {}

    def view(request):
        key = int(request.GET["request"])
        Session.objects.count()
        states[key] = (connections["default"], connection.connection, backend_pid(connection.connection))
        return HttpResponse(b"body")

    install_view(monkeypatch, view)

    async def exercise():
        ready = [asyncio.Event() for _ in range(8)]
        release = asyncio.Event()

        async def request(key):
            async def send(message):
                if message["type"] == "http.response.body":
                    ready[key].set()
                    await release.wait()

            request_scope = {**scope(), "query_string": f"request={key}".encode()}
            await application(request_scope, receive, send)

        tasks = [asyncio.create_task(request(key)) for key in range(8)]
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in ready)), 5)
            assert len({item[2] for item in states.values()}) == 8
            for task in tasks[:4]:
                task.cancel()
            cancelled = await asyncio.gather(*tasks[:4], return_exceptions=True)
            assert all(isinstance(error, asyncio.CancelledError) for error in cancelled)
            assert all(states[key][1].closed for key in range(4))
            assert all(not states[key][1].closed for key in range(4, 8))
            release.set()
            await asyncio.gather(*tasks[4:])
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    try:
        asyncio.run(exercise())
        assert all(item[1].closed for item in states.values())
        assert_backends_gone([item[2] for item in states.values()])
    finally:
        for wrapper, _, _ in states.values():
            wrapper.inc_thread_sharing()
            try:
                wrapper.close()
            finally:
                wrapper.dec_thread_sharing()
