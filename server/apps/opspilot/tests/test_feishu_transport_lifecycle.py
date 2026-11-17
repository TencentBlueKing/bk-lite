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

    yield sdk_tasks

    async def stop():
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.close()
        await server.wait_closed()

    run(stop())


def test_issue_6886_closed_transport_releases_sdk_tasks(local_gateway):
    sdk_tasks = local_gateway
    for _cycle in range(3):
        transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
        reference = weakref.ref(transport)
        transport.close()
        del transport
        assert sdk_tasks() == []
        assert reference() is None
