import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from nats_client.management.commands import nats_listener

pytestmark = pytest.mark.unit


async def _cancel_tasks_created_after(existing_tasks):
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current and task not in existing_tasks and not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def test_core_listener_bounds_slow_handlers_and_backpressures_callback(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    callbacks = {}
    release = asyncio.Event()
    active = 0
    max_active = 0
    completed = 0

    class FakeNats:
        async def subscribe(self, subject, queue, cb):
            callbacks[subject] = cb

    async def fake_get_nc_client(client):
        return client

    async def slow_handler(_func_name, _data, reply=None):
        nonlocal active, max_active, completed
        active += 1
        max_active = max(max_active, active)
        try:
            await release.wait()
        finally:
            active -= 1
            completed += 1

    monkeypatch.setattr(nats_listener, "get_nc_client", fake_get_nc_client)
    monkeypatch.setattr(
        nats_listener.default_registry,
        "registry",
        {
            "bklite.slow_handler": {
                "func": slow_handler,
                "namespace": "bklite",
                "name": "slow_handler",
                "js": False,
            }
        },
    )
    settings.NATS_JETSTREAM_ENABLED = False
    settings.NATS_HANDLER_CONCURRENCY = 2
    settings.NATS_HANDLER_QUEUE_SIZE = 3

    command = nats_listener.Command()
    command.nats = FakeNats()
    command.handler = slow_handler
    await command.nats_coroutine()

    callback = callbacks["bklite.slow_handler"]

    async def publish_burst():
        for _ in range(6):
            msg = type(
                "Msg",
                (),
                {
                    "data": b'{"args": [], "kwargs": {}}',
                    "reply": "_INBOX.reply",
                    "subject": "bklite.slow_handler",
                },
            )()
            await callback(msg)

    producer = asyncio.create_task(publish_burst())
    try:
        for _ in range(20):
            await asyncio.sleep(0)
            if active >= 2:
                break

        assert active == 2
        assert max_active == 2
        assert not producer.done(), "队列满后 callback 应等待容量，而不是继续创建任务"

        release.set()
        await asyncio.wait_for(producer, timeout=1)
        for _ in range(20):
            await asyncio.sleep(0)
            if completed == 6:
                break

        assert completed == 6
        assert max_active == 2
    finally:
        release.set()
        with suppress(asyncio.CancelledError):
            await producer
        if hasattr(command, "shutdown"):
            await command.shutdown()
        await _cancel_tasks_created_after(existing_tasks)


async def test_jetstream_ack_waits_for_successful_handler(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    release = asyncio.Event()
    handler_started = asyncio.Event()
    stop_fetch = asyncio.Event()
    message = type(
        "JetStreamMsg",
        (),
        {
            "data": b'{"args": [], "kwargs": {}}',
            "subject": "bklite.js.slow_handler",
            "ack": AsyncMock(),
        },
    )()

    class FakePullSubscription:
        def __init__(self):
            self.fetch_count = 0

        async def fetch(self, timeout):
            self.fetch_count += 1
            if self.fetch_count == 1:
                return [message]
            await stop_fetch.wait()
            raise nats_listener.nats.errors.TimeoutError

    class FakeJetStream:
        def __init__(self):
            self.subscription = FakePullSubscription()

        async def pull_subscribe(self, subject, durable):
            return self.subscription

    class FakeNats:
        def __init__(self):
            self.js = FakeJetStream()

        def jetstream(self):
            return self.js

    async def fake_get_nc_client(client):
        return client

    async def slow_handler(_func_name, _data, reply=None):
        handler_started.set()
        await release.wait()

    monkeypatch.setattr(nats_listener, "get_nc_client", fake_get_nc_client)
    monkeypatch.setattr(
        nats_listener.default_registry,
        "registry",
        {
            "bklite.js.slow_handler": {
                "func": slow_handler,
                "namespace": "bklite",
                "name": "slow_handler",
                "js": True,
            }
        },
    )
    settings.NATS_JETSTREAM_ENABLED = True
    settings.NATS_JETSTREAM_CRATE_STREAM = False
    settings.NATS_HANDLER_CONCURRENCY = 1
    settings.NATS_HANDLER_QUEUE_SIZE = 1

    command = nats_listener.Command()
    command.nats = FakeNats()
    command.handler = slow_handler
    await command.nats_coroutine()

    try:
        await asyncio.wait_for(handler_started.wait(), timeout=1)
        message.ack.assert_not_awaited()

        release.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if message.ack.await_count:
                break

        message.ack.assert_awaited_once()
    finally:
        release.set()
        stop_fetch.set()
        if hasattr(command, "shutdown"):
            await command.shutdown()
        await _cancel_tasks_created_after(existing_tasks)
