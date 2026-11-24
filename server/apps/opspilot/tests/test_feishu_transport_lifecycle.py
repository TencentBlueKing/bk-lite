"""用官方 SDK 和本地 WebSocket 确认关闭后不再留下后台任务。"""

import asyncio
import gc
import weakref

import pytest
import websockets
from lark_oapi.ws import client as sdk

from apps.opspilot.services import skill_channel_feishu_long_connection_sdk as transport_sdk


@pytest.fixture
def local_gateway(monkeypatch):
    loop = transport_sdk._ensure_loop()

    async def receive(connection):
        async for _message in connection:
            pass

    async def start():
        return await websockets.serve(receive, "127.0.0.1", 0, max_size=4096, max_queue=4)

    def run(coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=3)

    server = run(start())
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setattr(sdk.Client, "_get_conn_url", lambda self: f"ws://127.0.0.1:{port}/?device_id=fixture&service_id=1")

    def sdk_tasks():
        run(asyncio.sleep(0.05))
        gc.collect()

        async def pending():
            names = []
            for task in asyncio.all_tasks():
                if task is asyncio.current_task():
                    continue
                qualname = task.get_coro().__qualname__
                if "Client." in qualname or "ExpiringCache." in qualname:
                    names.append(qualname)
            return names

        return run(pending())

    yield sdk_tasks, run, server

    async def stop():
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.close()
        await server.wait_closed()

    run(stop())


def test_issue_6886_closed_transport_releases_sdk_tasks(local_gateway):
    sdk_tasks, _run, _server = local_gateway
    for _cycle in range(3):
        transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
        reference = weakref.ref(transport)
        transport.close()
        del transport
        assert sdk_tasks() == []
        assert reference() is None


@pytest.mark.parametrize("payload", [sdk._new_ping_frame(1).SerializeToString(), b"invalid-protobuf"])
def test_issue_7143_online_transport_releases_completed_message_tasks(local_gateway, payload):
    sdk_tasks, run, server = local_gateway
    references = []

    async def observe():
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()

        def create_task(loop, coroutine, **kwargs):
            task = previous(loop, coroutine, **kwargs) if previous else asyncio.Task(coroutine, loop=loop, **kwargs)
            if coroutine.__qualname__.endswith("._handle_message"):
                references.append(weakref.ref(task))
            return task

        loop.set_task_factory(create_task)
        return previous

    async def send():
        for connection in server.connections:
            await connection.send(payload)

    async def restore(previous):
        asyncio.get_running_loop().set_task_factory(previous)

    transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    previous = run(observe())
    try:
        for count in range(1, 6):
            run(send())
            sdk_tasks()
            assert len(references) == count
            assert all(reference() is None for reference in references)
    finally:
        transport.close()
        transport.close()
        run(restore(previous))
    assert sdk_tasks() == []


def test_issue_7143_close_releases_cancelled_message_task(local_gateway, monkeypatch):
    sdk_tasks, run, server = local_gateway
    references = []

    async def blocked_handler(self, frame):
        references.append(weakref.ref(asyncio.current_task()))
        await asyncio.Event().wait()

    async def send():
        for connection in server.connections:
            await connection.send(sdk._new_ping_frame(1).SerializeToString())

    monkeypatch.setattr(sdk.Client, "_handle_control_frame", blocked_handler)
    transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    try:
        run(send())
        sdk_tasks()
        assert len(references) == 1
        assert references[0]() is not None
    finally:
        transport.close()
        transport.close()
    assert sdk_tasks() == []
    assert references[0]() is None
