import asyncio

import pytest
from core.collection.contracts import RunSummary
from core.collection.enums import RunStatus
from core.collection.runtime import CollectionRequest, CollectionRuntime, CollectionRuntimeSettings, InMemoryRunStateStore, SubmissionStatus


class RecordingRunStateStore(InMemoryRunStateStore):
    def __init__(self):
        super().__init__()
        self.heartbeats = 0
        self.finishes = []

    async def heartbeat(self, lease, *, ttl_seconds):
        self.heartbeats += 1
        return await super().heartbeat(lease, ttl_seconds=ttl_seconds)

    async def finish(self, lease, status, summary=None):
        self.finishes.append((status, summary))
        return await super().finish(lease, status, summary)


@pytest.mark.asyncio
async def test_run_with_target_errors_finishes_as_completed_with_errors():
    tasks = []
    store = RecordingRunStateStore()

    async def execute(_request, _lease):
        return RunSummary(
            total=2,
            collection_succeeded=2,
            collection_failed=0,
            unreachable=0,
            deferred=0,
            skipped=0,
            publish_succeeded=1,
            publish_failed=1,
        )

    runtime = CollectionRuntime(
        state_store=store,
        execute=execute,
        schedule=lambda coroutine, *, name: tasks.append(asyncio.create_task(coroutine, name=name)) or tasks[-1],
        owner_id="pod-a",
    )
    await runtime.submit(
        CollectionRequest(
            task_id="completed-with-errors",
            plugin_ref="network.config",
            targets=("10.10.24.1", "10.10.24.2"),
        )
    )

    await tasks[0]

    assert store.finishes[0][0] == RunStatus.COMPLETED_WITH_ERRORS


@pytest.mark.asyncio
async def test_run_lifecycle_logs_merge_searchable_context(monkeypatch):
    tasks = []
    logged = []

    def capture(message, *args):
        logged.append(message % args if args else message)

    async def execute(_request, _lease):
        return RunSummary(
            total=2,
            collection_succeeded=1,
            collection_failed=1,
            unreachable=0,
            deferred=0,
            skipped=0,
        )

    monkeypatch.setattr("core.collection.runtime.logger.info", capture)
    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=lambda coroutine, *, name: tasks.append(asyncio.create_task(coroutine, name=name)) or tasks[-1],
        owner_id="pod-a",
    )
    await runtime.submit(
        CollectionRequest(
            task_id="searchable-run",
            plugin_ref="network.config",
            targets=("10.0.0.1", "10.0.0.2"),
            credentials=({"credential_id": "credential-1"},),
            params={
                "model_id": "network",
                "plugin_name": "snmp_facts",
                "instance_id": "cmdb_network_7",
            },
        )
    )

    await tasks[0]

    assert len(logged) == 2
    assert "event=collection_run_started" in logged[0]
    assert "task_id=" not in logged[0]
    assert "plugin_ref=network.config" in logged[0]
    assert "plugin_name=snmp_facts" in logged[0]
    assert "instance_id=cmdb_network_7" in logged[0]
    assert "任务开始" in logged[0]
    assert "目标数=2 凭据数=1" in logged[0]
    assert "event=collection_run_terminal" in logged[1]
    assert "task_id=" not in logged[1]
    assert "instance_id=cmdb_network_7" in logged[1]
    assert "status=completed_with_errors" in logged[1]
    assert "任务结束" in logged[1]
    assert "最终状态=部分失败" in logged[1]
    assert "执行批次=1" in logged[1]
    assert "duration_ms=" in logged[1]


@pytest.mark.asyncio
async def test_same_task_id_and_request_only_schedule_one_collection_run(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    scheduled_tasks = []
    warning_calls = []

    monkeypatch.setattr(
        "core.collection.runtime.logger.warning",
        lambda message, *args: warning_calls.append((message, args)),
    )

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
    task_id = "collect-001\r\nforged=true"
    request = CollectionRequest(
        task_id=task_id,
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        credentials=({"credential_id": "credential-1", "password": "duplicate-secret-sentinel"},),
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
    assert warning_calls == [
        (
            "event=collection_run_duplicate_skipped task_id=%s status=duplicate_active fence=%s",
            ("collect-001\\r\\nforged=true", first.fence),
        )
    ]
    rendered = warning_calls[0][0] % warning_calls[0][1]
    assert rendered == ("event=collection_run_duplicate_skipped " "task_id=collect-001\\r\\nforged=true status=duplicate_active fence=1")
    assert duplicate.task_id == task_id
    assert "duplicate-secret-sentinel" not in rendered

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
        schedule=lambda coroutine, *, name: asyncio.create_task(coroutine, name=name),
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
        schedule=lambda coroutine, *, name: asyncio.create_task(coroutine, name=name),
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
async def test_finished_task_can_be_resubmitted_on_next_cycle():
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

    first = await runtime.submit(request)
    await tasks[0]
    second = await runtime.submit(request)

    assert first.status == SubmissionStatus.ACCEPTED
    assert second.status == SubmissionStatus.ACCEPTED
    assert len(tasks) == 2
    await tasks[1]


@pytest.mark.asyncio
async def test_run_deadline_cancels_slow_collection_and_releases_capacity():
    tasks = []

    async def execute(_request, _lease):
        await asyncio.sleep(1)

    runtime = CollectionRuntime(
        state_store=InMemoryRunStateStore(),
        execute=execute,
        schedule=lambda coroutine, *, name: tasks.append(asyncio.create_task(coroutine, name=name)) or tasks[-1],
        settings=CollectionRuntimeSettings(run_deadline_seconds=0.01),
        owner_id="pod-a",
    )
    await runtime.submit(CollectionRequest(task_id="deadline", plugin_ref="mysql.config", targets=("127.0.0.1",)))
    await tasks[0]
    assert runtime.active_runs == 0
