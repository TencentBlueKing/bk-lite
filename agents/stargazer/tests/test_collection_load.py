import asyncio
import time

import pytest

from core.collection_runtime import CollectionRequest, RunLease
from core.target_collection_executor import (
    CollectOutcome,
    CollectOutcomeStatus,
    PreflightResult,
    PreflightStatus,
    TargetCollectionExecutor,
    TargetExecutorSettings,
)


@pytest.mark.asyncio
async def test_255_targets_5_credentials_200_concurrency_keeps_loop_responsive():
    active = 0
    peak = 0
    plugin_calls = 0
    lag_samples = []
    stop_heartbeat = asyncio.Event()

    class TimeoutPreflight:
        async def check(self, target, request, *, timeout_seconds):
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
        task_id="load-255x5x200",
        plugin_ref="mysql.config",
        targets=tuple(f"10.10.24.{index}" for index in range(1, 256)),
        credentials=tuple(
            {"credential_id": f"credential-{index}"}
            for index in range(1, 6)
        ),
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
            max_active_targets=200,
            target_task_window=200,
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
    leaked = [
        task
        for task in asyncio.all_tasks() - before
        if task is not asyncio.current_task() and not task.done()
    ]

    assert peak == 200
    assert plugin_calls == 0
    assert summary.total == 255
    assert summary.unreachable == 255
    assert max(lag_samples, default=0) < 0.1
    assert leaked == []
