"""以真实官方 SDK 与本地 WebSocket 验证 transport 的生命周期。"""

import asyncio
import gc
import json
import weakref
from concurrent.futures import CancelledError

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

    async def settle():
        await asyncio.sleep(0.05)

    def collect():
        run(settle())
        gc.collect()

        async def pending():
            return [
                task.get_coro().__qualname__
                for task in asyncio.all_tasks()
                if task is not asyncio.current_task()
                and ("Client." in task.get_coro().__qualname__ or "ExpiringCache." in task.get_coro().__qualname__)
            ]

        return run(pending())

    yield run, collect, server

    async def stop():
        # 即使红测失败也回收本测试启动的 SDK 任务和本地连接。
        tasks = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and ("Client." in task.get_coro().__qualname__ or "ExpiringCache." in task.get_coro().__qualname__)
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.close()
        await server.wait_closed()

    run(stop())


def test_closed_transport_releases_sdk_callbacks_and_background_tasks(local_gateway):
    _run, collect, _server = local_gateway
    for _cycle in range(3):
        transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
        reference = weakref.ref(transport)
        transport.close()
        del transport
        assert collect() == []
        assert reference() is None, "已关闭 transport 仍被 SDK 后台任务的回调持有"


def test_repeated_close_preserves_another_apps_connection(local_gateway):
    _run, collect, server = local_gateway
    first = transport_sdk.open_feishu_sdk_transport("first", "fixture")
    second = transport_sdk.open_feishu_sdk_transport("second", "fixture")
    try:
        first.close()
        first.close()
        reference = weakref.ref(first)
        del first
        collect()
        assert reference() is None
        assert len(server.connections) == 1
        assert second.poll(0) is None
    finally:
        second.close()
    assert collect() == []
    assert not server.connections


@pytest.mark.parametrize("failure", [RuntimeError("fixture failure"), asyncio.CancelledError()])
def test_start_failure_and_cancellation_reclaim_client(local_gateway, monkeypatch, failure):
    _run, collect, _server = local_gateway
    clients = []

    async def fail(client):
        clients.append(weakref.ref(client))
        raise failure

    monkeypatch.setattr(sdk.Client, "_connect", fail)
    monkeypatch.setattr(sdk.Client, "_reconnect", fail)
    # run_coroutine_threadsafe 将 asyncio 取消映射为 concurrent.futures.CancelledError。
    expected = CancelledError if isinstance(failure, asyncio.CancelledError) else RuntimeError
    with pytest.raises(expected):
        transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    failure.__traceback__ = None
    assert collect() == []
    assert clients and all(reference() is None for reference in clients)


def test_start_timeout_cancels_connection_work(local_gateway, monkeypatch):
    _run, collect, server = local_gateway
    clients = []
    stopped = []

    async def block(client):
        clients.append(weakref.ref(client))
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    monkeypatch.setattr(sdk.Client, "_connect", block)
    monkeypatch.setattr(transport_sdk, "_CONNECT_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(TimeoutError):
        transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    assert collect() == []
    assert stopped == [True]
    assert clients and all(reference() is None for reference in clients)
    assert not server.connections


def test_active_client_still_reconnects_before_close(local_gateway):
    run, collect, server = local_gateway
    transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    transport._ws._reconnect_nonce = 0
    transport._ws._reconnect_interval = 0.01
    original = next(iter(server.connections))
    try:
        run(original.close())

        async def reconnected():
            async with asyncio.timeout(1):
                while not server.connections or original in server.connections:
                    await asyncio.sleep(0.01)

        run(reconnected())
        assert len(server.connections) == 1
    finally:
        transport.close()
    assert collect() == []
    assert not server.connections


def test_start_cancellation_is_preserved_when_disconnect_fails(local_gateway, monkeypatch, caplog):
    _run, collect, _server = local_gateway
    sentinel = "fixture-private-payload-do-not-log"

    async def cancel(client):
        raise asyncio.CancelledError()

    async def fail_cleanup(client):
        raise OSError(sentinel)

    monkeypatch.setattr(sdk.Client, "_connect", cancel)
    monkeypatch.setattr(sdk.Client, "_disconnect", fail_cleanup)
    with pytest.raises(CancelledError):
        transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    assert collect() == []
    assert "cleanup_failed" in caplog.text
    assert "OSError" in caplog.text
    assert sentinel not in caplog.text


def test_real_sdk_inbound_and_cancel_pending_ack(local_gateway, monkeypatch):
    run, collect, server = local_gateway
    transport = transport_sdk.open_feishu_sdk_transport("fixture", "fixture")
    reference = weakref.ref(transport)
    ack_started = []
    ack_finished = []

    async def blocked_ack(self, frame):
        ack_started.append(True)
        try:
            await asyncio.Event().wait()
        finally:
            ack_finished.append(True)

    # 已建立连接后的 DATA ACK 网络写入阻塞，保留真实 decode 和回调。
    monkeypatch.setattr(sdk.Client, "_write_message", blocked_ack)
    frame = sdk.Frame(method=sdk.FrameType.DATA.value, SeqID=1, LogID=1, service=1)
    headers = {
        sdk.HEADER_MESSAGE_ID: "fixture-msg",
        sdk.HEADER_TRACE_ID: "fixture-trace",
        sdk.HEADER_SUM: "1",
        sdk.HEADER_SEQ: "0",
        sdk.HEADER_TYPE: sdk.MessageType.EVENT.value,
    }
    for key, value in headers.items():
        header = frame.headers.add()
        header.key = key
        header.value = value
    frame.payload = json.dumps(
        {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "event_id": "fixture"},
            "event": {
                "message": {
                    "message_id": "fixture",
                    "chat_id": "chat",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": json.dumps({"text": "fixture"}),
                    "mentions": [],
                },
                "sender": {"sender_type": "user", "sender_id": {"open_id": "user"}},
            },
        }
    ).encode()
    run(next(iter(server.connections)).send(frame.SerializeToString()))
    event = transport.poll(1)
    assert event is not None and event.text == "fixture"
    transport.close()
    del transport
    assert collect() == []
    assert ack_started and ack_finished == ack_started
    assert reference() is None
    assert not server.connections
