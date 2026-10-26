"""诊断必须观测真实连接，而不能通过额外查询或持有连接来改变事故现场。"""

import asyncio
import gc
import logging
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from asgiref.sync import ThreadSensitiveContext, sync_to_async
from django.contrib.sessions.models import Session
from django.db import connection, connections
from django.http import HttpResponse

from apps.core.tests import test_asgi_response_cleanup_service as cleanup_tests
from apps.core.tests.test_asgi_response_cleanup_service import backend_pid, install_view, receive, scope

application = cleanup_tests.application


@pytest.fixture(autouse=True)
def diagnostics_env(monkeypatch):
    monkeypatch.setenv("DB_CONNECTION_DIAGNOSTICS", "true")


def records_for(caplog, event):
    return [record for record in caplog.records if record.msg.startswith("event=" + event + " ")]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("failure", ["normal", "send_error", "cancel"])
def test_request_diagnostics_correlate_real_pg_cleanup_without_secrets(application, monkeypatch, caplog, failure):
    from apps.core.db_diagnostics import install_diagnostics

    # 重复构造应用或注册不得重复记日志。
    install_diagnostics()
    install_diagnostics()
    caplog.set_level(logging.INFO, logger="app")
    state = {}
    sentinel = "diagnostic-secret-must-not-be-logged"
    error = OSError(sentinel)

    def view(request):
        query_count = 0

        def count_query(execute, sql, params, many, context):
            nonlocal query_count
            query_count += 1
            return execute(sql, params, many, context)

        with connection.execute_wrapper(count_query):
            Session.objects.count()
        assert query_count == 1, "建连诊断不能额外执行 SQL"
        state.update(wrapper=connections["default"], driver=connection.connection, pid=backend_pid(connection.connection))
        state["thread"] = threading.get_ident()
        state["request_id"] = request.request_id
        return HttpResponse(sentinel)

    install_view(monkeypatch, view)

    async def exercise():
        sending = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body":
                sending.set()
                if failure == "send_error":
                    raise error
                if failure == "cancel":
                    await asyncio.Future()

        request_scope = {**scope(), "query_string": ("token=" + sentinel).encode(), "headers": [(b"authorization", sentinel.encode())]}
        task = asyncio.create_task(application(request_scope, receive, send))
        await asyncio.wait_for(sending.wait(), 5)
        if failure == "cancel":
            task.cancel(sentinel)
            with pytest.raises(asyncio.CancelledError):
                await task
        elif failure == "send_error":
            with pytest.raises(OSError) as caught:
                await task
            assert caught.value is error
        else:
            await task

    asyncio.run(exercise())
    assert state["driver"].closed
    created = records_for(caplog, "db_connection_observed")
    final = records_for(caplog, "db_connection_request_end")
    ended = records_for(caplog, "db_request_end")
    assert len(created) == len(final) == len(ended) == 1
    for record in created + final + ended:
        assert record.args and "%s" in record.msg
        assert "request_id=" + state["request_id"] in record.getMessage()
        assert record.exc_info is None, "诊断汇总不抢占业务异常的 traceback 所有权"
    assert f"pg_pid={state['pid']}" in final[0].getMessage()
    assert f"owner_thread={state['thread']}" in final[0].getMessage()
    assert "state=closed" in final[0].getMessage()
    assert "cleanup_seen=True" in final[0].getMessage()
    assert "cleanup_state=closed" in final[0].getMessage()
    assert "status_code=200" in ended[0].getMessage()
    assert "route=resource/" in ended[0].getMessage()
    assert ("outcome=returned" if failure == "normal" else "outcome=raised") in ended[0].getMessage()
    assert f"cleanup_fallback={failure != 'normal'}" in ended[0].getMessage()
    assert ("last_stage=response_close" if failure == "normal" else "failed_stage=send_response") in ended[0].getMessage()
    assert sentinel not in "\n".join(logging.Formatter().format(record) for record in caplog.records)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("side_thread", [False, True])
def test_open_connection_distinguishes_persistent_policy_and_missing_thread_cleanup(application, monkeypatch, caplog, side_thread):
    caplog.set_level(logging.INFO, logger="app")
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 0 if side_thread else 60)
    state = {}
    executor = ThreadPoolExecutor(max_workers=1)

    def query():
        Session.objects.count()
        state.update(wrapper=connections["default"], driver=connection.connection, pid=backend_pid(connection.connection))

    async def view(request):
        await sync_to_async(query, thread_sensitive=not side_thread, executor=executor if side_thread else None)()
        return HttpResponse(b"ok")

    install_view(monkeypatch, view)

    async def send(message):
        return None

    try:
        asyncio.run(application(scope(), receive, send))
        assert not state["driver"].closed, "诊断不能主动关闭连接、改变原连接策略"
        final = records_for(caplog, "db_connection_request_end")
        assert len(final) == 1
        message = final[0].getMessage()
        assert "state=open" in message
        assert f"cleanup_seen={not side_thread}" in message
        assert f"conn_max_age={0 if side_thread else 60}" in message
        assert f"pg_pid={state['pid']}" in message
    finally:
        wrapper = state.get("wrapper")
        if wrapper is not None:
            wrapper.inc_thread_sharing()
            try:
                wrapper.close()
            finally:
                wrapper.dec_thread_sharing()
        executor.shutdown()


def test_disabled_diagnostics_do_not_emit_or_touch_database(application, monkeypatch, caplog):
    monkeypatch.delenv("DB_CONNECTION_DIAGNOSTICS")
    install_view(monkeypatch, lambda request: HttpResponse(b"ok"))
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(application(scope(), receive, send))
    assert messages[0]["status"] == 200
    assert not [record for record in caplog.records if record.msg.startswith("event=db_")]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_cancellation_before_response_identifies_missing_cleanup(application, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app")
    state = {}

    def query():
        Session.objects.count()
        state.update(wrapper=connections["default"], driver=connection.connection)

    async def exercise():
        ready = asyncio.Event()

        async def view(request):
            await sync_to_async(query, thread_sensitive=True)()
            ready.set()
            await asyncio.Future()

        install_view(monkeypatch, view)

        async def send(message):
            pytest.fail("响应生成前取消不能发送响应")

        task = asyncio.create_task(application(scope(), receive, send))
        await asyncio.wait_for(ready.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(exercise())
        message = records_for(caplog, "db_connection_request_end")[0].getMessage()
        assert "state=open" in message and "cleanup_seen=False" in message
        ended = records_for(caplog, "db_request_end")[0].getMessage()
        assert "failed_stage=application" in ended
        assert "error_type=CancelledError" in ended
        assert "response_closed=False" in ended
        assert not state["driver"].closed
    finally:
        wrapper = state.get("wrapper")
        if wrapper is not None:
            wrapper.inc_thread_sharing()
            try:
                wrapper.close()
            finally:
                wrapper.dec_thread_sharing()


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_concurrent_requests_do_not_mix_connection_ids(application, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app")
    state = {}

    def view(request):
        Session.objects.count()
        state[request.request_id] = (backend_pid(connection.connection), connections["default"])
        return HttpResponse(b"ok")

    install_view(monkeypatch, view)

    async def exercise():
        ready = [asyncio.Event() for _ in range(4)]
        release = asyncio.Event()

        async def request(index):
            async def send(message):
                ready[index].set()
                await release.wait()

            await application(scope(), receive, send)

        tasks = [asyncio.create_task(request(index)) for index in range(4)]
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in ready)), 5)
        finally:
            release.set()
            await asyncio.gather(*tasks)

    asyncio.run(exercise())
    assert len(state) == len({pid for pid, _ in state.values()}) == 4
    final = records_for(caplog, "db_connection_request_end")
    assert len(final) == 4
    for request_id, (pid, wrapper) in state.items():
        message = next(record.getMessage() for record in final if "request_id=" + request_id in record.getMessage())
        assert f"pg_pid={pid}" in message
        assert "state=closed" in message and "cleanup_seen=True" in message
        assert wrapper.connection is None


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_unscoped_executor_connection_keeps_callsite_without_false_request_link(application, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app")
    state = {}

    def query():
        Session.objects.count()
        state["pid"] = backend_pid(connection.connection)
        connections.close_all()

    async def view(request):
        # 原生 executor 不传播 ContextVar，与 sync_to_async 的行为不同。
        await asyncio.get_running_loop().run_in_executor(None, query)
        return HttpResponse(b"ok")

    install_view(monkeypatch, view)

    async def send(message):
        return None

    asyncio.run(application(scope(), receive, send))
    observed = records_for(caplog, "db_connection_observed")
    assert len(observed) == 1
    message = observed[0].getMessage()
    assert "request_id=-" in message and "origin=unscoped_created" in message
    assert f"pg_pid={state['pid']}" in message and ":query" in message


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_diagnostic_failure_does_not_fail_orm_or_expose_exception(application, monkeypatch, caplog):
    from apps.core import db_diagnostics

    sentinel = "secret-diagnostic-internal-exception"
    caplog.set_level(logging.INFO, logger="app")

    def broken_observer(*args):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(db_diagnostics, "log_observed", broken_observer)

    def view(request):
        assert Session.objects.count() == 0
        return HttpResponse(b"unchanged")

    install_view(monkeypatch, view)
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(application(scope(), receive, send))
    assert messages[0]["status"] == 200
    assert messages[-1]["body"] == b"unchanged"
    failures = records_for(caplog, "db_diagnostic_failed")
    assert len(failures) == 1
    assert "failed_stage=observe" in failures[0].getMessage()
    assert "error_type=RuntimeError" in failures[0].getMessage()
    assert failures[0].exc_info is None
    assert sentinel not in "\n".join(logging.Formatter().format(record) for record in caplog.records)


class FakeDriver:
    def __init__(self, pid=321):
        self.info = SimpleNamespace(backend_pid=pid)
        self.closed = False


class FakeWrapper:
    vendor = "postgresql"
    alias = "default"
    settings_dict = {"CONN_MAX_AGE": 0}
    in_atomic_block = False
    errors_occurred = False
    autocommit = True

    def __init__(self):
        self.connection = FakeDriver()


def test_observations_are_bounded_and_do_not_keep_wrapper_alive(caplog):
    from apps.core.db_diagnostics import MAX_CONNECTIONS_PER_REQUEST, RequestTrace

    caplog.set_level(logging.INFO, logger="app")
    trace = RequestTrace(scope())
    wrapper = FakeWrapper()
    ref = weakref.ref(wrapper)
    for _ in range(MAX_CONNECTIONS_PER_REQUEST + 2):
        trace.observe(wrapper, "created")
    del wrapper
    gc.collect()
    assert ref() is None, "诊断不能延长 wrapper/连接的寿命"
    trace.finish("returned", "-")
    assert len(records_for(caplog, "db_connection_observed")) == MAX_CONNECTIONS_PER_REQUEST
    final = records_for(caplog, "db_connection_request_end")
    assert len(final) == MAX_CONNECTIONS_PER_REQUEST
    assert all("state=wrapper_gone_unknown" in record.getMessage() for record in final)
    assert "dropped_connections=2" in records_for(caplog, "db_request_end")[0].getMessage()


def test_reconnected_wrapper_is_not_misreported_as_old_connection_open():
    from apps.core.db_diagnostics import ConnectionObservation

    wrapper = FakeWrapper()
    observation = ConnectionObservation(wrapper)
    old_driver = wrapper.connection
    wrapper.connection = FakeDriver(322)
    assert observation.snapshot()[0] == "replaced_unknown"
    assert not old_driver.closed


def test_reused_driver_address_does_not_attribute_new_connection_to_old_pg_pid(monkeypatch):
    from apps.core import db_diagnostics

    # 地址复用已独立实测；这里固定分配器结果，避免回归测试依赖 CPython 分配时机。
    monkeypatch.setattr(db_diagnostics, "id", lambda value: 123, raising=False)
    wrapper = FakeWrapper()
    old_driver = weakref.ref(wrapper.connection)
    observation = db_diagnostics.ConnectionObservation(wrapper)
    wrapper.connection = None
    gc.collect()
    assert old_driver() is None, "观测不得保活底层驱动"
    wrapper.connection = FakeDriver(322)
    assert observation.pg_pid == 321
    assert observation.snapshot()[0] == "replaced_unknown"
    assert not wrapper.connection.closed


def test_cleanup_snapshot_survives_wrapper_collection(caplog):
    from apps.core.db_diagnostics import RequestTrace, current_trace, on_request_finished

    caplog.set_level(logging.INFO, logger="app")
    trace = RequestTrace(scope())
    token = current_trace.set(trace)
    try:
        wrapper = FakeWrapper()
        trace.observe(wrapper, "created")
        wrapper.connection = None
        on_request_finished(sender=None)
        del wrapper
        gc.collect()
        trace.finish("returned", "-")
        message = records_for(caplog, "db_connection_request_end")[0].getMessage()
        assert "state=wrapper_gone_unknown" in message
        assert "cleanup_seen=True" in message and "cleanup_state=closed" in message
    finally:
        current_trace.reset(token)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_existing_persistent_connection_is_observed_in_next_request(application, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app")
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 60)
    state = {}

    def view(request):
        Session.objects.count()
        state["wrapper"] = connections["default"]
        state["pid"] = backend_pid(connection.connection)
        return HttpResponse(b"ok")

    install_view(monkeypatch, view)

    async def send(message):
        return None

    async def exercise():
        async with ThreadSensitiveContext():
            await application(scope(), receive, send)
            await application(scope(), receive, send)
            await sync_to_async(connections.close_all, thread_sensitive=True)()

    asyncio.run(exercise())
    observed = records_for(caplog, "db_connection_observed")
    assert len(observed) == 2
    assert "origin=created" in observed[0].getMessage()
    assert "origin=existing_at_start" in observed[1].getMessage()
    assert all(f"pg_pid={state['pid']}" in record.getMessage() for record in observed)
    assert state["wrapper"].connection is None
