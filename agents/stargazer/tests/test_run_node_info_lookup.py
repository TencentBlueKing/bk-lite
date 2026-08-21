import asyncio

import pytest

import core.collection.node_info_lookup as node_info_lookup_module
from core.collection.node_info_lookup import RunNodeInfoLookup
from core.collection.metrics import CollectionMetrics


@pytest.mark.asyncio
async def test_run_lookup_coalesces_150_concurrent_targets_into_one_batch():
    targets = tuple(f"10.0.0.{index}" for index in range(1, 151))
    calls = []

    async def load(ips, **_context):
        calls.append(tuple(ips))
        await asyncio.sleep(0)
        return [
            {
                "id": f"node-{ip}",
                "ip": ip,
                "operating_system": "linux",
            }
            for ip in ips
        ]

    lookup = RunNodeInfoLookup(
        task_id="run-150",
        targets=targets,
        loader=load,
    )

    nodes = await asyncio.gather(*(lookup.get(target) for target in targets))

    assert len(calls) == 1
    assert calls[0] == targets
    assert [node["ip"] for node in nodes] == list(targets)


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_shared_lookup():
    started = asyncio.Event()
    release = asyncio.Event()

    async def load(ips, **_context):
        started.set()
        await release.wait()
        return [{"id": "node-1", "ip": ips[0], "operating_system": "linux"}]

    lookup = RunNodeInfoLookup(
        task_id="cancel-one-target",
        targets=("10.0.0.1",),
        loader=load,
    )
    first = asyncio.create_task(lookup.get("10.0.0.1"))
    second = asyncio.create_task(lookup.get("10.0.0.1"))
    await started.wait()

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()

    assert (await second)["id"] == "node-1"


@pytest.mark.asyncio
async def test_failed_batch_is_cached_without_per_target_retry():
    calls = 0

    async def load(_ips, **_context):
        nonlocal calls
        calls += 1
        raise ConnectionError("node manager unavailable")

    lookup = RunNodeInfoLookup(
        task_id="failed-batch",
        targets=("10.0.0.1", "10.0.0.2"),
        loader=load,
    )

    assert await lookup.get("10.0.0.1") is None
    assert await lookup.get("10.0.0.2") is None
    assert calls == 1


@pytest.mark.asyncio
async def test_large_run_is_split_into_bounded_batches():
    targets = tuple(f"10.{index // 65536}.{(index // 256) % 256}.{index % 256}" for index in range(1, 502))
    batch_sizes = []

    async def load(ips, **_context):
        batch_sizes.append(len(ips))
        return [{"id": f"node-{ip}", "ip": ip, "operating_system": "linux"} for ip in ips]

    lookup = RunNodeInfoLookup(
        task_id="bounded-batches",
        targets=targets,
        loader=load,
    )

    assert (await lookup.get(targets[-1]))["ip"] == targets[-1]
    assert batch_sizes == [500, 1]


@pytest.mark.asyncio
async def test_hostname_uses_validated_connect_ip_once_per_run():
    calls = []

    async def load(ips, **_context):
        calls.append(tuple(ips))
        return [{"id": "node-dns", "ip": ips[0], "operating_system": "linux"}]

    lookup = RunNodeInfoLookup(
        task_id="hostname-target",
        targets=("host.example",),
        loader=load,
    )

    first, second = await asyncio.gather(
        lookup.get("host.example", connect_host="10.0.0.8"),
        lookup.get("host.example", connect_host="10.0.0.8"),
    )

    assert first["id"] == "node-dns"
    assert second["id"] == "node-dns"
    assert calls == [("10.0.0.8",)]


@pytest.mark.asyncio
async def test_close_cancels_shared_lookup_for_whole_run(monkeypatch):
    started = asyncio.Event()
    cancelled = asyncio.Event()
    summaries = []

    monkeypatch.setattr(
        node_info_lookup_module.logger,
        "info",
        lambda message, *args: summaries.append(message % args),
    )

    async def load(_ips, **_context):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    lookup = RunNodeInfoLookup(
        task_id="cancel-run",
        targets=("10.0.0.1",),
        loader=load,
    )
    waiter = asyncio.create_task(lookup.get("10.0.0.1"))
    await started.wait()

    await lookup.close()

    assert cancelled.is_set()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert len(summaries) == 1
    assert "status=cancelled" in summaries[0]


@pytest.mark.asyncio
async def test_failed_batch_is_counted_as_failed_not_missing():
    metrics = CollectionMetrics()

    async def load(_ips, **_context):
        raise ConnectionError("node manager unavailable")

    lookup = RunNodeInfoLookup(
        task_id="failed-status",
        targets=("10.0.0.1", "10.0.0.2"),
        loader=load,
        metrics=metrics,
    )

    assert await lookup.get("10.0.0.1") is None
    await lookup.close()

    snapshot = metrics.snapshot()
    assert snapshot["job_node_info_lookup_failure_total"] == 2
    assert snapshot.get("job_node_info_lookup_missing_total", 0) == 0
    assert snapshot["job_node_info_lookup_total"] == 1


@pytest.mark.asyncio
async def test_hostname_queries_share_one_run_total_budget():
    calls = []

    async def load(ips, **_context):
        calls.append(tuple(ips))
        await asyncio.sleep(0.03)
        return []

    lookup = RunNodeInfoLookup(
        task_id="hostname-budget",
        targets=("one.example", "two.example"),
        loader=load,
        batch_timeout_seconds=0.1,
        total_timeout_seconds=0.01,
    )

    first, second = await asyncio.gather(
        lookup.get("one.example", connect_host="10.0.0.1"),
        lookup.get("two.example", connect_host="10.0.0.2"),
    )
    await lookup.close()

    assert first is None
    assert second is None
    assert calls == [("10.0.0.1",)]


@pytest.mark.asyncio
async def test_different_runs_do_not_share_node_info_cache():
    calls = 0

    async def load(ips, **_context):
        nonlocal calls
        calls += 1
        return [{"id": f"node-{calls}", "ip": ips[0], "operating_system": "linux"}]

    first = RunNodeInfoLookup(task_id="run-one", targets=("10.0.0.1",), loader=load)
    second = RunNodeInfoLookup(task_id="run-two", targets=("10.0.0.1",), loader=load)

    assert (await first.get("10.0.0.1"))["id"] == "node-1"
    assert (await second.get("10.0.0.1"))["id"] == "node-2"
    await first.close()
    await second.close()
    assert calls == 2


@pytest.mark.asyncio
async def test_lookup_duration_excludes_collection_time_after_lookup(monkeypatch):
    clock = {"now": 10.0}
    metrics = CollectionMetrics()
    monkeypatch.setattr(
        node_info_lookup_module.time,
        "monotonic",
        lambda: clock["now"],
    )

    async def load(ips, **_context):
        clock["now"] = 12.0
        return [{"id": "node-1", "ip": ips[0], "operating_system": "linux"}]

    lookup = RunNodeInfoLookup(
        task_id="duration-only-lookup",
        targets=("10.0.0.1",),
        loader=load,
        metrics=metrics,
    )
    await lookup.get("10.0.0.1")
    clock["now"] = 100.0
    await lookup.close()

    assert metrics.snapshot()["job_node_info_lookup_duration_seconds_p95"] == 2.0
