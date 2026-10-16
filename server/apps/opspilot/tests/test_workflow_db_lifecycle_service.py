"""真实数据库验证工作流旁路线程的连接生命周期。

不使用 django_db(transaction=True)：共享 reuse-db 上的 flush 会截断
system_mgmt 表并撞到未纳入本文件 INSTALL_APPS 的外键。
工作线程连接是 thread-local，外层 TestCase 事务不影响本断言。
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.sessions.models import Session
from django.db import connection, connections, transaction


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method,args",
    [
        ("_record_node_execution_result_async", ("node", None)),
        ("_record_execution_result_async", ({}, {}, True)),
        ("_record_conversation_history_async", ("user", "message", "user", "openai")),
    ],
)
@pytest.mark.parametrize("fails", [False, True])
def test_async_persistence_closes_own_thread_connection(monkeypatch, method, args, fails):
    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

    if connection.vendor != "postgresql":
        pytest.skip("连接生命周期集成测试需要 PostgreSQL")
    engine = ChatFlowEngine.__new__(ChatFlowEngine)
    worker_ids = []
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 0)

    def persist(*args):
        worker_ids.append(threading.get_ident())
        with transaction.atomic():
            Session.objects.count()
            assert connection.connection is not None
            if fails:
                raise ValueError("persistence failed")

    monkeypatch.setattr(engine, method.removesuffix("_async"), persist)

    async def exercise():
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(executor)
        try:
            if fails:
                with pytest.raises(ValueError, match="persistence failed"):
                    await getattr(engine, method)(*args)
            else:
                await getattr(engine, method)(*args)
            # 同一存活线程上检查，不靠线程退出或 GC 回收掩盖遗漏。
            worker_id, closed = await loop.run_in_executor(None, lambda: (threading.get_ident(), connection.connection is None))
            assert worker_ids == [worker_id]
            assert closed
        finally:
            await loop.run_in_executor(None, connections.close_all)

    asyncio.run(exercise())


@pytest.mark.django_db
def test_cancelled_persistence_cleans_up_after_worker_finishes(monkeypatch):
    from apps.opspilot.utils.chat_flow_utils.engine.engine import ChatFlowEngine

    if connection.vendor != "postgresql":
        pytest.skip("连接生命周期集成测试需要 PostgreSQL")
    engine = ChatFlowEngine.__new__(ChatFlowEngine)
    monkeypatch.setitem(connections.settings["default"], "CONN_MAX_AGE", 0)
    started = threading.Event()
    release = threading.Event()

    def persist(*args):
        with transaction.atomic():
            Session.objects.count()
            started.set()
            assert release.wait(5)
            assert connection.connection is not None

    monkeypatch.setattr(engine, "_record_conversation_history", persist)

    async def exercise():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        task = asyncio.create_task(engine._record_conversation_history_async("user", "message", "user", "openai"))
        try:
            for _ in range(500):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
            # 取消 await 不会终止 Python 工作线程；等该线程完成后才验收清理。
            assert await loop.run_in_executor(None, lambda: connection.connection is None)
        finally:
            release.set()
            await loop.run_in_executor(None, connections.close_all)

    asyncio.run(exercise())
