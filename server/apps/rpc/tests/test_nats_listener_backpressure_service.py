import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nats_client.management.commands import nats_listener

from .nats_listener_test_utils import cancel_tasks_created_after

pytestmark = pytest.mark.unit


def _message(subject, *, reply="", ack=None, in_progress=None):
    return SimpleNamespace(
        data=b'{"args": [], "kwargs": {}}',
        subject=subject,
        reply=reply,
        ack=ack or AsyncMock(),
        in_progress=in_progress or AsyncMock(),
    )


def _nats_with_pull_subscription(subscription):
    class FakeJetStream:
        async def pull_subscribe(self, subject, durable):
            return subscription

    class FakeNats:
        def jetstream(self):
            return FakeJetStream()

    return FakeNats()


async def _fake_get_nc_client(client):
    return client


async def _start_listener(monkeypatch, settings, *, handler, nats, name, js, concurrency, queue_size):
    monkeypatch.setattr(nats_listener, "get_nc_client", _fake_get_nc_client)
    monkeypatch.setattr(
        nats_listener.default_registry,
        "registry",
        {
            f"bklite.{('js.' if js else '')}{name}": {
                "func": handler,
                "namespace": "bklite",
                "name": name,
                "js": js,
            }
        },
    )
    settings.NATS_JETSTREAM_ENABLED = js
    settings.NATS_JETSTREAM_CRATE_STREAM = False
    settings.NATS_HANDLER_CONCURRENCY = concurrency
    settings.NATS_HANDLER_QUEUE_SIZE = queue_size
    command = nats_listener.Command()
    command.nats = nats
    command.handler = handler
    await command.nats_coroutine()
    return command


async def test_core_listener_bounds_slow_handlers_and_backpressures_callback(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    callbacks = {}
    subscription_options = {}
    release = asyncio.Event()
    active = 0
    max_active = 0
    completed = 0

    class FakeNats:
        async def subscribe(self, subject, queue, cb, **kwargs):
            callbacks[subject] = cb
            subscription_options.update(kwargs)

    async def slow_handler(_func_name, _data, reply=None):
        nonlocal active, max_active, completed
        active += 1
        max_active = max(max_active, active)
        try:
            await release.wait()
        finally:
            active -= 1
            completed += 1

    settings.NATS_CORE_PENDING_MSGS_LIMIT = 7
    settings.NATS_CORE_PENDING_BYTES_LIMIT = 4096
    command = await _start_listener(
        monkeypatch,
        settings,
        handler=slow_handler,
        nats=FakeNats(),
        name="slow_handler",
        js=False,
        concurrency=2,
        queue_size=3,
    )

    callback = callbacks["bklite.slow_handler"]
    assert subscription_options == {
        "pending_msgs_limit": 7,
        "pending_bytes_limit": 4096,
    }

    async def publish_burst():
        for _ in range(6):
            msg = _message("bklite.slow_handler", reply="_INBOX.reply")
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
        await cancel_tasks_created_after(existing_tasks)


async def test_jetstream_ack_waits_for_successful_handler(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    release = asyncio.Event()
    handler_started = asyncio.Event()
    stop_fetch = asyncio.Event()
    message = _message("bklite.js.slow_handler")

    class FakePullSubscription:
        def __init__(self):
            self.fetch_count = 0

        async def fetch(self, timeout):
            self.fetch_count += 1
            if self.fetch_count == 1:
                return [message]
            await stop_fetch.wait()
            raise nats_listener.nats.errors.TimeoutError

    async def slow_handler(_func_name, _data, reply=None):
        handler_started.set()
        await release.wait()

    command = await _start_listener(
        monkeypatch,
        settings,
        handler=slow_handler,
        nats=_nats_with_pull_subscription(FakePullSubscription()),
        name="slow_handler",
        js=True,
        concurrency=1,
        queue_size=1,
    )

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
        await cancel_tasks_created_after(existing_tasks)


async def test_jetstream_single_subject_uses_configured_handler_concurrency(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    release = asyncio.Event()
    both_started = asyncio.Event()
    stop_fetch = asyncio.Event()
    active = 0
    max_active = 0
    messages = [_message("bklite.js.concurrent_handler") for _ in range(2)]

    class FakePullSubscription:
        async def fetch(self, timeout):
            if messages:
                return [messages.pop(0)]
            await stop_fetch.wait()
            raise nats_listener.nats.errors.TimeoutError

    async def concurrent_handler(_func_name, _data, reply=None):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            both_started.set()
        try:
            await release.wait()
        finally:
            active -= 1

    command = await _start_listener(
        monkeypatch,
        settings,
        handler=concurrent_handler,
        nats=_nats_with_pull_subscription(FakePullSubscription()),
        name="concurrent_handler",
        js=True,
        concurrency=2,
        queue_size=2,
    )

    try:
        await asyncio.wait_for(both_started.wait(), timeout=1)
        assert max_active == 2
    finally:
        release.set()
        stop_fetch.set()
        await command.shutdown()
        await cancel_tasks_created_after(existing_tasks)


async def test_jetstream_fetch_handler_and_ack_failures_do_not_stop_consumer(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    third_handled = asyncio.Event()
    stop_fetch = asyncio.Event()
    failed_handler_ack = AsyncMock()
    failed_ack = AsyncMock(side_effect=ConnectionError("ack disconnected"))
    successful_ack = AsyncMock()
    first_message = _message("bklite.js.retry_handler", ack=failed_handler_ack)
    second_message = _message("bklite.js.retry_handler", ack=failed_ack)
    third_message = _message("bklite.js.retry_handler", ack=successful_ack)

    class FakePullSubscription:
        def __init__(self):
            self.fetch_count = 0

        async def fetch(self, timeout):
            self.fetch_count += 1
            if self.fetch_count == 1:
                raise ConnectionError("fetch disconnected")
            if self.fetch_count == 2:
                return [first_message]
            if self.fetch_count == 3:
                return [second_message]
            if self.fetch_count == 4:
                return [third_message]
            await stop_fetch.wait()
            raise nats_listener.nats.errors.TimeoutError

    handled = 0

    async def handler(_func_name, _data, reply=None):
        nonlocal handled
        handled += 1
        if handled == 1:
            raise RuntimeError("handler failed")
        if handled == 3:
            third_handled.set()

    settings.NATS_FETCH_RETRY_DELAY = 0
    command = await _start_listener(
        monkeypatch,
        settings,
        handler=handler,
        nats=_nats_with_pull_subscription(FakePullSubscription()),
        name="retry_handler",
        js=True,
        concurrency=1,
        queue_size=2,
    )

    try:
        await asyncio.wait_for(third_handled.wait(), timeout=1)
        failed_handler_ack.assert_not_awaited()
        failed_ack.assert_awaited_once()
        successful_ack.assert_awaited_once()
    finally:
        stop_fetch.set()
        await command.shutdown()
        await cancel_tasks_created_after(existing_tasks)


async def test_jetstream_slow_handler_sends_in_progress_until_ack(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    release = asyncio.Event()
    handler_started = asyncio.Event()
    progress_sent = asyncio.Event()
    stop_fetch = asyncio.Event()
    progress_attempts = 0

    async def in_progress():
        nonlocal progress_attempts
        progress_attempts += 1
        if progress_attempts == 1:
            raise ConnectionError("heartbeat disconnected")
        progress_sent.set()

    message = _message("bklite.js.slow_handler", in_progress=AsyncMock(side_effect=in_progress))

    class FakePullSubscription:
        def __init__(self):
            self.delivered = False

        async def fetch(self, timeout):
            if not self.delivered:
                self.delivered = True
                return [message]
            await stop_fetch.wait()
            raise nats_listener.nats.errors.TimeoutError

    async def slow_handler(_func_name, _data, reply=None):
        handler_started.set()
        await release.wait()

    settings.NATS_JETSTREAM_IN_PROGRESS_INTERVAL = 0.01
    command = await _start_listener(
        monkeypatch,
        settings,
        handler=slow_handler,
        nats=_nats_with_pull_subscription(FakePullSubscription()),
        name="slow_handler",
        js=True,
        concurrency=1,
        queue_size=1,
    )

    try:
        await asyncio.wait_for(handler_started.wait(), timeout=1)
        await asyncio.wait_for(progress_sent.wait(), timeout=1)
        assert message.in_progress.await_count >= 2
        message.ack.assert_not_awaited()
        release.set()
        await asyncio.wait_for(command._message_queue.join(), timeout=1)
        message.ack.assert_awaited_once()
    finally:
        release.set()
        stop_fetch.set()
        await command.shutdown()
        await cancel_tasks_created_after(existing_tasks)


async def test_shutdown_drains_accepted_core_messages_before_cancelling_workers(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    callbacks = {}
    release = asyncio.Event()
    handler_started = asyncio.Event()
    completed = 0

    class FakeSubscription:
        async def drain(self):
            return None

    class FakeNats:
        async def subscribe(self, subject, queue, cb, **kwargs):
            callbacks[subject] = cb
            return FakeSubscription()

    async def handler(_func_name, _data, reply=None):
        nonlocal completed
        handler_started.set()
        await release.wait()
        completed += 1

    settings.NATS_HANDLER_SHUTDOWN_TIMEOUT = 1
    command = await _start_listener(
        monkeypatch,
        settings,
        handler=handler,
        nats=FakeNats(),
        name="drain_handler",
        js=False,
        concurrency=1,
        queue_size=3,
    )
    callback = callbacks["bklite.drain_handler"]
    message = _message("bklite.drain_handler", reply="_INBOX.reply")
    for _ in range(3):
        await callback(message)
    await asyncio.wait_for(handler_started.wait(), timeout=1)

    shutdown_task = asyncio.create_task(command.shutdown())
    try:
        await asyncio.sleep(0)
        assert not shutdown_task.done()
        release.set()
        await asyncio.wait_for(shutdown_task, timeout=1)
        assert completed == 3
    finally:
        release.set()
        if not shutdown_task.done():
            await shutdown_task
        await cancel_tasks_created_after(existing_tasks)


async def test_shutdown_timeout_cancels_stuck_handler(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    callbacks = {}
    handler_started = asyncio.Event()
    handler_cancelled = asyncio.Event()

    class FakeSubscription:
        async def drain(self):
            return None

    class FakeNats:
        async def subscribe(self, subject, queue, cb, **kwargs):
            callbacks[subject] = cb
            return FakeSubscription()

    async def stuck_handler(_func_name, _data, reply=None):
        handler_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise

    settings.NATS_HANDLER_SHUTDOWN_TIMEOUT = 0.01
    command = await _start_listener(
        monkeypatch,
        settings,
        handler=stuck_handler,
        nats=FakeNats(),
        name="stuck_handler",
        js=False,
        concurrency=1,
        queue_size=1,
    )
    message = _message("bklite.stuck_handler", reply="_INBOX.reply")
    await callbacks["bklite.stuck_handler"](message)
    await asyncio.wait_for(handler_started.wait(), timeout=1)

    await command.shutdown()

    assert handler_cancelled.is_set()
    assert not command._worker_tasks
    await cancel_tasks_created_after(existing_tasks)


async def test_core_worker_preserves_success_and_failure_reply_envelopes(monkeypatch, settings):
    existing_tasks = set(asyncio.all_tasks())
    published = []

    class FakeNats:
        async def publish(self, reply, payload):
            published.append((reply, payload))

    dispatch = AsyncMock(side_effect=[{"value": 1}, ValueError("invalid payload")])
    monkeypatch.setattr(nats_listener, "nats_handler", dispatch)
    settings.NATS_HANDLER_CONCURRENCY = 1
    settings.NATS_HANDLER_QUEUE_SIZE = 2

    command = nats_listener.Command()
    command.nats = FakeNats()
    command._start_workers()
    await command._enqueue("bklite.success", '{"args": [], "kwargs": {}}', reply="_INBOX.success")
    await command._enqueue("bklite.failure", '{"args": [], "kwargs": {}}', reply="_INBOX.failure")
    await asyncio.wait_for(command._message_queue.join(), timeout=1)

    try:
        success = nats_listener.json.loads(published[0][1])
        failure = nats_listener.json.loads(published[1][1])
        assert published[0][0] == "_INBOX.success"
        assert success == {"success": True, "result": {"value": 1}}
        assert published[1][0] == "_INBOX.failure"
        assert failure["success"] is False
        assert failure["error"] == "ValueError"
        assert failure["message"] == "invalid payload"
    finally:
        await command.shutdown()
        await cancel_tasks_created_after(existing_tasks)
