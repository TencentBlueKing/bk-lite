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
    TargetExecutorSettings,
)
from core.collection.executor import TargetCollectionExecutor
from core.collection.runtime import CollectionRequest, RunLease


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
        async def enqueue(self, request, result, lease):
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
