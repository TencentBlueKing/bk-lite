import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.components import nats as nats_config
from nats_client.management.commands import nats_listener

from .nats_listener_test_utils import cancel_tasks_created_after

pytestmark = pytest.mark.unit


async def test_shared_queue_preserves_waiter_fairness_across_subjects(settings):
    existing_tasks = set(asyncio.all_tasks())
    permits = asyncio.Queue()
    started = {name: asyncio.Event() for name in ("hot-1", "hot-2", "hot-3", "cold", "hot-4")}
    observed_order = []

    async def handler(func_name, _data, reply=None):
        observed_order.append(func_name)
        started[func_name].set()
        await permits.get()

    settings.NATS_HANDLER_CONCURRENCY = 1
    settings.NATS_HANDLER_QUEUE_SIZE = 1
    command = nats_listener.Command()
    command.handler = handler
    command._start_workers()

    await command._enqueue("hot-1", "{}")
    await asyncio.wait_for(started["hot-1"].wait(), timeout=1)
    await command._enqueue("hot-2", "{}")
    hot_3 = asyncio.create_task(command._enqueue("hot-3", "{}"))
    await asyncio.sleep(0)
    cold = asyncio.create_task(command._enqueue("cold", "{}"))
    await asyncio.sleep(0)

    permits.put_nowait(None)
    await asyncio.wait_for(started["hot-2"].wait(), timeout=1)
    await asyncio.wait_for(hot_3, timeout=1)
    hot_4 = asyncio.create_task(command._enqueue("hot-4", "{}"))
    await asyncio.sleep(0)

    permits.put_nowait(None)
    await asyncio.wait_for(started["hot-3"].wait(), timeout=1)
    await asyncio.wait_for(cold, timeout=1)
    assert not hot_4.done(), "后到的热点 subject 不应越过已经等待的其他 subject"

    permits.put_nowait(None)
    await asyncio.wait_for(started["cold"].wait(), timeout=1)
    await asyncio.wait_for(hot_4, timeout=1)
    permits.put_nowait(None)
    await asyncio.wait_for(started["hot-4"].wait(), timeout=1)
    permits.put_nowait(None)
    await asyncio.wait_for(command._message_queue.join(), timeout=1)

    try:
        assert observed_order == ["hot-1", "hot-2", "hot-3", "cold", "hot-4"]
    finally:
        await command.shutdown()
        await cancel_tasks_created_after(existing_tasks)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("invalid", 64), ("0", 1), ("-3", 1)],
)
def test_invalid_numeric_config_falls_back_without_blocking_startup(monkeypatch, raw_value, expected):
    monkeypatch.setenv("NATS_HANDLER_CONCURRENCY", raw_value)

    assert nats_config._read_number("NATS_HANDLER_CONCURRENCY", 64, int, 1) == expected


async def test_core_queue_overload_returns_failure_reply(monkeypatch, settings):
    callbacks = {}
    published = []
    release = asyncio.Event()
    started = asyncio.Event()

    class FakeNats:
        async def subscribe(self, subject, queue, cb, **kwargs):
            callbacks[subject] = cb

        async def publish(self, reply, payload):
            published.append((reply, json.loads(payload)))

    async def fake_get_nc_client(client):
        return client

    async def handler(_func_name, _data, reply=None):
        started.set()
        await release.wait()

    monkeypatch.setattr(nats_listener, "get_nc_client", fake_get_nc_client)
    monkeypatch.setattr(
        nats_listener.default_registry,
        "registry",
        {
            "bklite.overload": {
                "func": handler,
                "namespace": "bklite",
                "name": "overload",
                "js": False,
            }
        },
    )
    settings.NATS_JETSTREAM_ENABLED = False
    settings.NATS_HANDLER_CONCURRENCY = 1
    settings.NATS_HANDLER_QUEUE_SIZE = 1
    settings.NATS_HANDLER_ENQUEUE_TIMEOUT = 0.01
    command = nats_listener.Command()
    command.nats = FakeNats()
    command.handler = handler
    await command.nats_coroutine()
    callback = callbacks["bklite.overload"]

    try:
        await callback(SimpleNamespace(data=b"{}", subject="bklite.overload", reply="reply-1"))
        await asyncio.wait_for(started.wait(), timeout=1)
        await callback(SimpleNamespace(data=b"{}", subject="bklite.overload", reply="reply-2"))
        await callback(SimpleNamespace(data=b"{}", subject="bklite.overload", reply="reply-3"))
        assert published[0][0] == "reply-3"
        assert published[0][1]["success"] is False
        assert published[0][1]["error"] == "_ListenerOverloadedError"
    finally:
        release.set()
        await command.shutdown()


async def test_listener_setup_failure_is_observed_and_stops_loop():
    stopped = asyncio.Event()

    class FakeLoop:
        def create_task(self, coroutine):
            return asyncio.create_task(coroutine)

        def stop(self):
            stopped.set()

    command = nats_listener.Command()
    command.nats_coroutine = AsyncMock(side_effect=RuntimeError("setup failed"))
    task = command._start_listener_setup(FakeLoop())

    await asyncio.gather(task, return_exceptions=True)
    await asyncio.wait_for(stopped.wait(), timeout=1)


async def test_jetstream_heartbeat_interval_respects_consumer_ack_wait(settings):
    settings.NATS_JETSTREAM_IN_PROGRESS_INTERVAL = 10
    subscription = AsyncMock()
    subscription.consumer_info.return_value = SimpleNamespace(
        config=SimpleNamespace(backoff=None, ack_wait=3),
    )
    command = nats_listener.Command()

    interval = await command._jetstream_progress_interval(subscription, "bklite.js.handler")

    assert interval == 1
