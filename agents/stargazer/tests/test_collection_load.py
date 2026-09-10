import asyncio
import gc
import time
import weakref

import pytest
from core.collection.contracts import (
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    PublishOutcome,
    PublishStatus,
    StructuredMetricsPayload,
    TargetCollectionResult,
    TargetExecutorSettings,
)
from core.collection.executor import TargetCollectionExecutor
from core.collection.metrics import CollectionMetrics
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher
from core.collection.runtime import CollectionRequest, RunLease
from core.infra import nats_utils
from core.infra.event_loop_monitor import EventLoopLagMonitor
from core.infra.jetstream_publish_window import JetStreamPublishWindow, JetStreamPublishWindowSettings


@pytest.mark.asyncio
async def test_3000_targets_5_credentials_160_concurrency_keeps_loop_responsive():
    active = 0
    peak = 0
    plugin_calls = 0
    lag_samples = []
    stop_heartbeat = asyncio.Event()

    class TimeoutPreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(timeout_seconds * 2)
            finally:
                active -= 1
            return PreflightResult(status=PreflightStatus.UNREACHABLE)

    class Plugin:
        async def collect(self, target, credential, context):
            nonlocal plugin_calls
            plugin_calls += 1
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS)

    class Publisher:
        async def publish(self, request, result, lease):
            return None

    async def heartbeat():
        interval = 0.01
        expected = time.monotonic() + interval
        while not stop_heartbeat.is_set():
            await asyncio.sleep(interval)
            now = time.monotonic()
            lag_samples.append(max(0.0, now - expected))
            expected = now + interval

    request = CollectionRequest(
        task_id="load-3000x5x160",
        plugin_ref="mysql.config",
        targets=tuple(f"target-{index}" for index in range(3000)),
        credentials=tuple({"credential_id": f"credential-{index}"} for index in range(1, 6)),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="load-pod",
        fence=1,
        expires_at=time.time() + 60,
    )
    executor = TargetCollectionExecutor(
        preflight=TimeoutPreflight(),
        plugin=Plugin(),
        publisher=Publisher(),
        settings=TargetExecutorSettings(
            max_active_targets=160,
            target_task_window=160,
            # 与生产 5 秒保持同一行为，按 1:100 缩放测试时钟。
            connect_timeout_seconds=0.05,
            plugin_timeout_seconds=0.05,
        ),
    )
    # 隔离前序测试遗留对象触发的整代 GC 停顿，避免把宿主机调度噪声
    # 误判为采集协程阻塞事件循环。
    gc.collect()
    before = set(asyncio.all_tasks())
    heartbeat_task = asyncio.create_task(heartbeat())

    summary = await executor.execute(request, lease)
    stop_heartbeat.set()
    await heartbeat_task
    await asyncio.sleep(0)
    leaked = [task for task in asyncio.all_tasks() - before if task is not asyncio.current_task() and not task.done()]

    assert peak == 160
    assert plugin_calls == 0
    assert summary.total == 3000
    assert summary.unreachable == 3000
    assert max(lag_samples, default=0) < 0.1
    assert leaked == []


@pytest.mark.asyncio
async def test_5000_large_success_payloads_are_bounded_before_run_finishes():
    release_last = asyncio.Event()
    last_started = asyncio.Event()
    payload_references = []
    completed = 0

    class ReachablePreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            return PreflightResult(status=PreflightStatus.REACHABLE)

    class LargePayloadPlugin:
        async def collect(self, target, credential, context):
            nonlocal completed
            if target == "target-4999":
                last_started.set()
                await release_last.wait()
            payload = StructuredMetricsPayload(data={"network": [{"target": target, "blob": "x" * 32768}]})
            payload_references.append(weakref.ref(payload))
            completed += 1
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=payload)

    class ImmediateReceipt:
        def done(self):
            return True

        async def wait(self):
            return PublishOutcome(status=PublishStatus.CONFIRMED)

        def cancel_if_unattempted(self):
            return False

    class ImmediatePublisher:
        async def enqueue(self, request, result, lease, *, deadline=None):
            return ImmediateReceipt()

    request = CollectionRequest(
        task_id="load-large-payload-lifecycle",
        plugin_ref="network.config",
        targets=tuple(f"target-{index}" for index in range(5000)),
        credentials=({"credential_id": "credential-1"},),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="load-pod",
        fence=1,
        expires_at=time.time() + 60,
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=LargePayloadPlugin(),
        publisher=ImmediatePublisher(),
        settings=TargetExecutorSettings(max_active_targets=160, target_task_window=160),
    )

    run = asyncio.create_task(executor.execute(request, lease))
    await asyncio.wait_for(last_started.wait(), timeout=5)
    for _ in range(100):
        if completed >= 4999:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0)
    gc.collect()

    live_payloads = sum(reference() is not None for reference in payload_references)
    assert completed >= 4999
    assert live_payloads <= 160
    assert run.done() is False

    release_last.set()
    summary = await run
    await asyncio.sleep(0)
    gc.collect()

    assert summary.collection_succeeded == 5000
    assert summary.publish_succeeded == 5000
    assert sum(reference() is not None for reference in payload_references) == 0


@pytest.mark.asyncio
async def test_payload_lifecycle_capacity_includes_targets_waiting_for_publisher_admission():
    release_publish = asyncio.Event()
    payload_references = []
    completed = 0

    class ReachablePreflight:
        async def check(self, target, request, *, timeout_seconds, plan=None):
            return PreflightResult(status=PreflightStatus.REACHABLE)

    class PayloadPlugin:
        async def collect(self, target, credential, context):
            nonlocal completed
            payload = StructuredMetricsPayload(data={"network": [{"target": target, "blob": "x" * 32768}]})
            payload_references.append(weakref.ref(payload))
            completed += 1
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=payload)

    class BlockingDelegate:
        async def publish_batch(self, items):
            await release_publish.wait()
            return {}

    publisher = BufferedResultPublisher(
        BlockingDelegate(),
        capacity=2,
        batch_size=1,
        worker_count=1,
    )
    request = CollectionRequest(
        task_id="payload-lifecycle-admission",
        plugin_ref="network.config",
        targets=tuple(f"target-{index}" for index in range(8)),
        credentials=({"credential_id": "credential-1"},),
    )
    executor = TargetCollectionExecutor(
        preflight=ReachablePreflight(),
        plugin=PayloadPlugin(),
        publisher=publisher,
        settings=TargetExecutorSettings(
            max_active_targets=2,
            target_task_window=2,
            publish_queue_timeout_seconds=1,
            publish_total_timeout_seconds=2,
        ),
    )

    run = asyncio.create_task(
        executor.execute(
            request,
            RunLease(request.task_id, request.digest, "load-pod", 1, time.time() + 60),
        )
    )
    for _ in range(100):
        if publisher.pending_payloads == 2:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    gc.collect()

    assert publisher.pending_payloads == 2
    assert completed <= 2
    assert sum(reference() is not None for reference in payload_references) <= 2

    release_publish.set()
    summary = await asyncio.wait_for(run, timeout=2)
    await publisher.shutdown()
    assert summary.publish_succeeded == 8


@pytest.mark.asyncio
async def test_160_mixed_topology_results_with_slow_puback_are_complete_and_bounded(monkeypatch):
    class SlowAckJetStream:
        def __init__(self):
            self.message_ids = []
            self.in_flight = 0
            self.peak_in_flight = 0

        async def publish_async(self, _subject, _payload=b"", *, headers=None, **_kwargs):
            self.message_ids.append(headers["Nats-Msg-Id"])
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            future = asyncio.get_running_loop().create_future()

            async def confirm():
                try:
                    await asyncio.sleep(0.002)
                    future.set_result(object())
                finally:
                    self.in_flight -= 1

            asyncio.create_task(confirm())
            return future

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING", "32")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING_PER_CALL", "8")
    slow_ack = SlowAckJetStream()
    window = JetStreamPublishWindow(
        lambda: slow_ack,
        settings=JetStreamPublishWindowSettings(
            max_pending_messages=32,
            max_pending_messages_per_call=8,
            max_pending_bytes=4 * 1024 * 1024,
            puback_timeout_seconds=1,
            max_attempts=1,
        ),
    )
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    metrics = CollectionMetrics(sample_capacity=5000)
    publisher = BufferedResultPublisher(
        NatsResultPublisher(metrics=metrics),
        capacity=160,
        batch_size=50,
        worker_count=4,
        flush_interval_seconds=0.005,
        metrics=metrics,
    )
    targets = tuple(f"10.20.0.{index + 1}" for index in range(160))
    request = CollectionRequest(
        task_id="load-topology-slow-puback",
        plugin_ref="network_topo.config",
        targets=targets,
        params={"model_id": "network_topo", "plugin_family": "configuration"},
    )
    lease = RunLease(request.task_id, request.digest, "load-pod", 1, time.time() + 60)
    large_targets = set(targets[::20])
    results = []
    expected_lines = 0
    for target in targets:
        row_count = 96 if target in large_targets else 1
        expected_lines += row_count
        results.append(
            TargetCollectionResult(
                target=target,
                status="success",
                attempts=1,
                value=StructuredMetricsPayload(
                    data={"network_topo": tuple({"target": target, "neighbor": f"neighbor-{index}"} for index in range(row_count))}
                ),
            )
        )

    # 压测计时前主动回收前序 fixture，保持事件循环延迟口径可重复。
    gc.collect()
    lag_monitor = EventLoopLagMonitor(interval_seconds=0.005)
    lag_monitor.start()
    started = time.perf_counter()
    try:
        receipts = await asyncio.gather(*(publisher.enqueue(request, result, lease) for result in results))
        outcomes = await asyncio.wait_for(
            asyncio.gather(*(receipt.wait() for receipt in receipts)),
            timeout=5,
        )
    finally:
        await publisher.shutdown()
        await lag_monitor.stop()
    elapsed = time.perf_counter() - started

    assert all(outcome.status == PublishStatus.CONFIRMED for outcome in outcomes)
    assert len(slow_ack.message_ids) == expected_lines
    assert len(set(slow_ack.message_ids)) == expected_lines
    assert window.snapshot().confirmed_total == expected_lines
    assert window.snapshot().pending_messages == 0
    assert window.snapshot().pending_bytes == 0
    assert slow_ack.peak_in_flight <= 32
    assert publisher.pending_payloads == 0
    assert lag_monitor.p99_seconds < 0.2
    assert elapsed < 5
