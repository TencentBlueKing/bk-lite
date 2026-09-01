import asyncio
import time
from collections import Counter
from types import SimpleNamespace

import pytest
from core.infra.jetstream_publish_window import JetStreamMessage, JetStreamPublishWindow, JetStreamPublishWindowSettings, JetStreamWindowPublishError


class RecordingJetStream:
    def __init__(self, *, ack_delay_seconds: float = 0.0, fail_first_ids=()) -> None:
        self.ack_delay_seconds = ack_delay_seconds
        self.fail_first_ids = set(fail_first_ids)
        self.attempts = Counter()
        self.headers = []
        self.in_flight = 0
        self.peak_in_flight = 0

    async def publish_async(self, subject, payload=b"", *, headers=None, **_kwargs):
        message_id = headers["Nats-Msg-Id"]
        self.attempts[message_id] += 1
        self.headers.append(dict(headers))
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        future = asyncio.get_running_loop().create_future()

        async def confirm():
            try:
                if self.ack_delay_seconds:
                    await asyncio.sleep(self.ack_delay_seconds)
                if message_id in self.fail_first_ids and self.attempts[message_id] == 1:
                    future.set_exception(TimeoutError("injected puback timeout"))
                else:
                    future.set_result(SimpleNamespace(stream="CMDB_METRICS", seq=1))
            finally:
                self.in_flight -= 1

        asyncio.create_task(confirm())
        return future


@pytest.mark.asyncio
async def test_global_window_limits_created_puback_tasks_across_concurrent_callers():
    started = asyncio.Event()

    class NeverAckJetStream:
        def __init__(self) -> None:
            self.in_flight = 0

        async def publish_async(self, *_args, **_kwargs):
            self.in_flight += 1
            if self.in_flight == 4:
                started.set()
            return asyncio.get_running_loop().create_future()

    jetstream = NeverAckJetStream()
    window = JetStreamPublishWindow(
        lambda: jetstream,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=4,
            max_pending_bytes=1024,
            puback_timeout_seconds=30,
            max_attempts=1,
        ),
    )
    callers = tuple(
        asyncio.create_task(
            window.publish(
                "metrics.network",
                tuple(JetStreamMessage(payload=b"line", message_id=f"caller-{caller}-message-{index}") for index in range(4)),
            )
        )
        for caller in range(4)
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)

    puback_tasks = tuple(
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done() and task.get_name().startswith("jetstream-puback:")
    )

    assert len(puback_tasks) == 4
    assert window.snapshot().pending_messages == 4

    for caller in callers:
        caller.cancel()
    await asyncio.gather(*callers, return_exceptions=True)
    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_5000_network_results_publish_concurrently_with_bounded_memory():
    jetstream = RecordingJetStream(ack_delay_seconds=0.0005)
    window = JetStreamPublishWindow(
        lambda: jetstream,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=128,
            max_pending_bytes=2 * 1024 * 1024,
            puback_timeout_seconds=2,
            max_attempts=2,
        ),
    )
    messages = (
        JetStreamMessage(
            payload=f"network_device_info,ip=10.0.{index // 255}.{index % 255} gauge=1".encode(),
            message_id=f"network-run:device-{index}:0",
        )
        for index in range(5000)
    )

    started = time.perf_counter()
    confirmed = await window.publish("metrics.network", messages)
    elapsed = time.perf_counter() - started

    assert confirmed == 5000
    assert jetstream.peak_in_flight > 1
    assert window.snapshot().peak_pending_messages <= 128
    assert window.snapshot().peak_pending_bytes <= 2 * 1024 * 1024
    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0
    assert elapsed < 2


@pytest.mark.asyncio
async def test_sangfor_snapshot_is_split_and_all_chunks_receive_puback():
    jetstream = RecordingJetStream(ack_delay_seconds=0.0005)
    window = JetStreamPublishWindow(
        lambda: jetstream,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=32,
            max_pending_bytes=1024 * 1024,
            puback_timeout_seconds=2,
            max_attempts=2,
        ),
    )
    snapshot_bytes = 6_092_710
    chunk_bytes = 128 * 1024
    messages = tuple(
        JetStreamMessage(
            payload=b"x" * min(chunk_bytes, snapshot_bytes - offset),
            message_id=f"sangfor-hci-10.233.1.171:{offset // chunk_bytes}",
        )
        for offset in range(0, snapshot_bytes, chunk_bytes)
    )

    confirmed = await window.publish("metrics.sangforscp", messages)

    assert confirmed == len(messages) == 47
    assert sum(len(message.payload) for message in messages) == snapshot_bytes
    assert window.snapshot().peak_pending_bytes <= 1024 * 1024
    assert all(header["Nats-Msg-Id"].startswith("sangfor-hci") for header in jetstream.headers)


@pytest.mark.asyncio
async def test_retry_reuses_message_id_after_one_puback_timeout():
    message_id = "run-1:device-1:0"
    jetstream = RecordingJetStream(fail_first_ids={message_id})
    window = JetStreamPublishWindow(
        lambda: jetstream,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=4,
            max_pending_bytes=1024,
            puback_timeout_seconds=1,
            max_attempts=2,
        ),
    )

    confirmed = await window.publish(
        "metrics.network",
        [JetStreamMessage(payload=b"device gauge=1", message_id=message_id)],
    )

    assert confirmed == 1
    assert jetstream.attempts[message_id] == 2
    assert [item["Nats-Msg-Id"] for item in jetstream.headers] == [message_id, message_id]
    assert window.snapshot().retry_total == 1


@pytest.mark.asyncio
async def test_single_message_larger_than_byte_window_fails_without_deadlock():
    window = JetStreamPublishWindow(
        lambda: RecordingJetStream(),
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=2,
            max_pending_bytes=8,
            puback_timeout_seconds=1,
            max_attempts=1,
        ),
    )

    with pytest.raises(ValueError, match="byte window"):
        await window.publish(
            "metrics.network",
            [JetStreamMessage(payload=b"012345678", message_id="too-large")],
        )


@pytest.mark.asyncio
async def test_cancelling_publish_cancels_puback_waiters_and_releases_window():
    started = asyncio.Event()

    class NeverAckJetStream:
        async def publish_async(self, *_args, **_kwargs):
            started.set()
            return asyncio.get_running_loop().create_future()

    window = JetStreamPublishWindow(
        lambda: NeverAckJetStream(),
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=1,
            max_pending_bytes=1024,
            puback_timeout_seconds=30,
            max_attempts=2,
        ),
    )
    publishing = asyncio.create_task(
        window.publish(
            "metrics.network",
            [JetStreamMessage(payload=b"line", message_id="cancel-me")],
        )
    )
    await started.wait()

    publishing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await publishing

    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0
    assert window.snapshot().retry_total == 0


@pytest.mark.asyncio
async def test_message_iterator_failure_cleans_up_started_publishes_before_returning():
    started = asyncio.Event()
    puback_future = None

    class NeverAckJetStream:
        async def publish_async(self, *_args, **_kwargs):
            nonlocal puback_future
            puback_future = asyncio.get_running_loop().create_future()
            started.set()
            return puback_future

    def messages():
        yield JetStreamMessage(payload=b"first", message_id="first")
        raise RuntimeError("iterator failed")

    window = JetStreamPublishWindow(
        lambda: NeverAckJetStream(),
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=2,
            max_pending_bytes=1024,
            puback_timeout_seconds=30,
            max_attempts=1,
        ),
    )

    with pytest.raises(RuntimeError, match="iterator failed"):
        await window.publish("metrics.network", messages())

    await asyncio.sleep(0)
    assert not started.is_set() or (puback_future is not None and puback_future.cancelled())
    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_puback_timeout_bounds_jetstream_provider_wait_and_releases_window():
    async def stalled_provider():
        await asyncio.Event().wait()

    window = JetStreamPublishWindow(
        stalled_provider,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=1,
            max_pending_bytes=1024,
            puback_timeout_seconds=0.01,
            max_attempts=1,
        ),
    )

    with pytest.raises(Exception) as caught:
        await asyncio.wait_for(
            window.publish(
                "metrics.network",
                [JetStreamMessage(payload=b"line", message_id="provider-timeout")],
            ),
            timeout=0.5,
        )

    assert type(caught.value).__name__ == "JetStreamWindowPublishError"
    assert isinstance(caught.value.__cause__, TimeoutError)
    assert window.snapshot().puback_timeout_total == 1
    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_one_rejected_message_does_not_leave_later_microbatch_messages_unattempted():
    class RejectFirstJetStream:
        async def publish_async(self, _subject, payload=b"", **_kwargs):
            future = asyncio.get_running_loop().create_future()
            if payload == b"first":
                future.set_exception(RuntimeError("first rejected"))
            else:
                future.set_result(SimpleNamespace(stream="CMDB_METRICS", seq=1))
            return future

    window = JetStreamPublishWindow(
        lambda: RejectFirstJetStream(),
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=1,
            max_pending_bytes=1024,
            puback_timeout_seconds=1,
            max_attempts=1,
        ),
    )
    messages = [
        JetStreamMessage(payload=b"first", message_id="first"),
        JetStreamMessage(payload=b"second", message_id="second"),
        JetStreamMessage(payload=b"third", message_id="third"),
    ]

    with pytest.raises(JetStreamWindowPublishError) as caught:
        await window.publish("metrics.network", messages)

    assert caught.value.attempted_indices == (0, 1, 2)
    assert caught.value.confirmed_indices == (1, 2)
