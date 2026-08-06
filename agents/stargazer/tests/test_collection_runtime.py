import asyncio

import pytest

from core.collection_runtime import (
    CollectionRequest,
    CollectionRuntime,
    CollectionRuntimeSettings,
    InMemoryRunStateStore,
    SubmissionStatus,
)


class RecordingRunStateStore(InMemoryRunStateStore):
    def __init__(self):
        super().__init__()
        self.heartbeats = 0

    async def heartbeat(self, lease, *, ttl_seconds):
        self.heartbeats += 1
        return await super().heartbeat(lease, ttl_seconds=ttl_seconds)


@pytest.mark.asyncio
async def test_same_task_id_and_request_only_schedule_one_collection_run():
    started = asyncio.Event()
    release = asyncio.Event()
    scheduled_tasks = []

    async def execute(_request, _lease):
        started.set()
        await release.wait()

    def schedule(coroutine, *, name):
        task = asyncio.create_task(coroutine, name=name)
        scheduled_tasks.append(task)
        return task

    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=schedule,
        settings=CollectionRuntimeSettings(max_active_runs=2),
        owner_id="pod-a",
    )
    request = CollectionRequest(
        task_id="collect-001",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1"},),
        params={"model_id": "mysql"},
    )

    first = await runtime.submit(request)
    await started.wait()
    duplicate = await runtime.submit(request)

    assert first.status == SubmissionStatus.ACCEPTED
    assert duplicate.status == SubmissionStatus.DUPLICATE_ACTIVE
    assert duplicate.task_id == first.task_id
    assert duplicate.fence == first.fence
    assert len(scheduled_tasks) == 1

    release.set()
    await scheduled_tasks[0]


@pytest.mark.asyncio
async def test_active_collection_run_renews_its_fenced_lease():
    release = asyncio.Event()
    store = RecordingRunStateStore()

    async def execute(_request, _lease):
        await release.wait()

    runtime = CollectionRuntime(
        state_store=store,
        execute=execute,
        schedule=lambda coroutine, *, name: asyncio.create_task(
            coroutine, name=name
        ),
        settings=CollectionRuntimeSettings(
            max_active_runs=1,
            lease_ttl_seconds=0.1,
            lease_heartbeat_seconds=0.01,
        ),
        owner_id="pod-a",
    )
    request = CollectionRequest(
        task_id="collect-heartbeat",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )

    submission = await runtime.submit(request)
    await asyncio.sleep(0.035)

    assert submission.status == SubmissionStatus.ACCEPTED
    assert store.heartbeats >= 2
    release.set()
    await asyncio.sleep(0.02)
    assert runtime.active_runs == 0


@pytest.mark.asyncio
async def test_shutdown_stops_admission_and_cancels_after_grace_period():
    cancelled = asyncio.Event()

    async def execute(_request, _lease):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=lambda coroutine, *, name: asyncio.create_task(
            coroutine, name=name
        ),
        owner_id="pod-a",
    )
    request = CollectionRequest(
        task_id="collect-shutdown",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )
    assert (await runtime.submit(request)).status == SubmissionStatus.ACCEPTED
    await asyncio.sleep(0)

    await runtime.shutdown(grace_seconds=0.01)
    rejected = await runtime.submit(
        CollectionRequest(
            task_id="collect-after-stop",
            plugin_ref="mysql.config",
            targets=("10.10.24.2",),
        )
    )

    assert cancelled.is_set()
    assert rejected.status == SubmissionStatus.BUSY
    assert rejected.reason == "collection runtime is shutting down"
    assert runtime.active_runs == 0


@pytest.mark.asyncio
async def test_completed_reentry_returns_existing_run_summary():
    tasks = []

    async def execute(_request, _lease):
        return {"total": 2, "succeeded": 2, "failed": 0}

    def schedule(coroutine, *, name):
        task = asyncio.create_task(coroutine, name=name)
        tasks.append(task)
        return task

    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=schedule,
        owner_id="pod-a",
    )
    request = CollectionRequest(
        task_id="collect-summary",
        plugin_ref="mysql.config",
        targets=("10.10.24.1", "10.10.24.2"),
    )

    await runtime.submit(request)
    await tasks[0]
    completed = await runtime.submit(request)

    assert completed.status == SubmissionStatus.COMPLETED
    assert completed.summary == {"total": 2, "succeeded": 2, "failed": 0}


@pytest.mark.asyncio
async def test_run_deadline_cancels_slow_collection_and_releases_capacity():
    tasks = []

    async def execute(_request, _lease):
        await asyncio.sleep(1)

    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=lambda coroutine, *, name: tasks.append(
            asyncio.create_task(coroutine, name=name)
        ) or tasks[-1],
        settings=CollectionRuntimeSettings(run_deadline_seconds=0.01),
        owner_id="pod-a",
    )
    await runtime.submit(CollectionRequest(
        task_id="deadline", plugin_ref="mysql.config", targets=("127.0.0.1",)
    ))
    await tasks[0]
    assert runtime.active_runs == 0
