import asyncio
import time

import pytest
from core.collection.metrics import CollectionMetrics
from core.collection.scheduler import CollectionScheduler


@pytest.mark.asyncio
async def test_scheduler_yields_between_blocking_target_starts():
    scheduler = CollectionScheduler(max_in_flight=20)
    release = asyncio.Event()
    stop_heartbeat = asyncio.Event()
    heartbeat_gaps = []

    async def handle(item):
        # 模拟 Collector 在第一次真正 await 前的同步初始化切片。
        time.sleep(0.01)
        await release.wait()
        return item

    async def heartbeat():
        previous = time.monotonic()
        while not stop_heartbeat.is_set():
            await asyncio.sleep(0)
            current = time.monotonic()
            heartbeat_gaps.append(current - previous)
            previous = current

    heartbeat_task = asyncio.create_task(heartbeat())
    run = asyncio.create_task(scheduler.execute("responsive", range(20), handle))
    try:
        deadline = time.monotonic() + 2
        while scheduler.active < 20 and time.monotonic() < deadline:
            await asyncio.sleep(0.001)

        assert scheduler.active == 20
        assert heartbeat_gaps
        assert max(heartbeat_gaps) < 0.08
    finally:
        release.set()
        await run
        stop_heartbeat.set()
        await heartbeat_task
        await scheduler.shutdown()


@pytest.mark.asyncio
async def test_scheduler_exposes_target_wait_and_dispatch_yield_metrics():
    metrics = CollectionMetrics()
    scheduler = CollectionScheduler(max_in_flight=1, metrics=metrics)

    async def handler(item):
        await asyncio.sleep(0.01)
        return item

    assert await scheduler.execute("metrics-run", (1, 2), handler) == (1, 2)
    snapshot = metrics.snapshot()

    assert snapshot["scheduler_dispatch_total"] == 2
    assert snapshot["scheduler_yield_total"] == 2
    assert snapshot["target_schedule_wait_seconds_p99"] >= 0
    assert snapshot["target_dispatch_to_started_seconds_p99"] >= 0

    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_scheduler_dispatch_quantum_is_fixed_to_one():
    metrics = CollectionMetrics()
    scheduler = CollectionScheduler(max_in_flight=4, metrics=metrics)
    release = asyncio.Event()

    async def handler(item):
        await release.wait()
        return item

    run = asyncio.create_task(scheduler.execute("quantum-two", range(4), handler))
    deadline = time.monotonic() + 1
    while scheduler.active < 4 and time.monotonic() < deadline:
        await asyncio.sleep(0)

    assert scheduler.active == 4
    assert metrics.snapshot()["scheduler_dispatch_total"] == 4
    assert metrics.snapshot()["scheduler_yield_total"] == 4

    release.set()
    assert await run == (0, 1, 2, 3)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_new_small_run_gets_next_available_slot_during_large_run():
    scheduler = CollectionScheduler(max_in_flight=2)
    releases = {item: asyncio.Event() for item in ("a1", "a2", "a3", "b1")}
    started = []

    async def handle(item):
        started.append(item)
        await releases[item].wait()
        return item

    large = asyncio.create_task(scheduler.execute("run-a", ("a1", "a2", "a3"), handle))
    await asyncio.sleep(0.01)
    assert started == ["a1", "a2"]

    small = asyncio.create_task(scheduler.execute("run-b", ("b1",), handle))
    await asyncio.sleep(0)
    releases["a1"].set()
    await asyncio.sleep(0.01)

    assert started == ["a1", "a2", "b1"]

    releases["a2"].set()
    releases["a3"].set()
    releases["b1"].set()
    assert await small == ("b1",)
    assert await large == ("a1", "a2", "a3")
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_scheduler_never_creates_more_than_global_window():
    scheduler = CollectionScheduler(max_in_flight=3)
    release = asyncio.Event()
    active = 0
    peak = 0

    async def handle(item):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await release.wait()
        active -= 1
        return item

    run = asyncio.create_task(scheduler.execute("bounded", tuple(range(100)), handle))
    await asyncio.sleep(0.01)

    assert scheduler.active == 3
    assert scheduler.peak == 3
    assert peak == 3

    release.set()
    assert await run == tuple(range(100))
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_scheduler_consumes_targets_only_after_a_slot_is_available():
    scheduler = CollectionScheduler(max_in_flight=3)
    release = asyncio.Event()
    consumed = 0

    def targets():
        nonlocal consumed
        for item in range(100):
            consumed += 1
            yield item

    async def handle(item):
        await release.wait()
        return item

    run = asyncio.create_task(scheduler.execute("lazy-targets", targets(), handle))
    await asyncio.sleep(0.01)

    assert consumed == 3
    assert scheduler.active == 3

    release.set()
    assert await run == tuple(range(100))
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_three_thousand_targets_remain_bounded_by_one_hundred_fifty_window():
    scheduler = CollectionScheduler(max_in_flight=150)
    release = asyncio.Event()

    async def handle(item):
        await release.wait()
        return item

    run = asyncio.create_task(scheduler.execute("three-thousand", range(3000), handle))
    await asyncio.sleep(0.05)

    assert scheduler.active == 150
    assert scheduler.peak == 150

    release.set()
    results = await run
    assert len(results) == 3000
    assert results[0] == 0
    assert results[-1] == 2999
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_scheduler_reports_waiting_running_and_completed_target_counts():
    scheduler = CollectionScheduler(max_in_flight=1)
    releases = [asyncio.Event(), asyncio.Event()]
    started = []

    async def handle(item):
        started.append(item)
        await releases[item].wait()
        return item

    run = asyncio.create_task(scheduler.execute("counted", range(2), handle))
    await asyncio.sleep(0.01)

    assert scheduler.pending == 1
    assert scheduler.active == 1
    assert scheduler.completed == 0
    assert scheduler.completed_total == 0

    releases[0].set()
    await asyncio.sleep(0.01)

    assert started == [0, 1]
    assert scheduler.pending == 0
    assert scheduler.active == 1
    assert scheduler.completed == 1
    assert scheduler.completed_total == 1

    releases[1].set()
    assert await run == (0, 1)
    assert scheduler.completed == 0
    assert scheduler.completed_total == 2
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_network_topology_borrows_half_general_capacity_when_general_is_idle():
    scheduler = CollectionScheduler(max_in_flight=10, topology_max_in_flight=3)
    release = asyncio.Event()

    async def handle(item):
        await release.wait()
        return item

    run = asyncio.create_task(
        scheduler.execute(
            "topology",
            range(20),
            handle,
            workload="network_topology",
        )
    )
    await asyncio.sleep(0.01)

    # 基础拓扑配额为 3；普通池 7 个槽位空闲时可借一半（向下取整），
    # 因此拓扑空闲态上限为 3 + floor(7 / 2) = 6。
    assert scheduler.active == 6
    assert scheduler.topology_active == 6

    release.set()
    assert await run == tuple(range(20))
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_network_topology_idle_borrow_can_be_disabled():
    scheduler = CollectionScheduler(
        max_in_flight=10,
        topology_max_in_flight=3,
        allow_topology_idle_borrow=False,
    )
    release = asyncio.Event()

    async def handle(item):
        await release.wait()
        return item

    run = asyncio.create_task(
        scheduler.execute(
            "topology",
            tuple(range(20)),
            handle,
            workload="network_topology",
        )
    )
    await asyncio.sleep(0.01)

    assert scheduler.active == 3
    assert scheduler.topology_active == 3

    release.set()
    assert await run == tuple(range(20))
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_general_arrival_stops_new_topology_borrowing_without_preemption():
    scheduler = CollectionScheduler(max_in_flight=10, topology_max_in_flight=3)
    topology_releases = [asyncio.Event() for _ in range(20)]
    general_release = asyncio.Event()
    started = []

    async def handle(item):
        started.append(item)
        if str(item).startswith("t"):
            await topology_releases[int(str(item)[1:])].wait()
        else:
            await general_release.wait()
        return item

    topology = asyncio.create_task(
        scheduler.execute(
            "topology",
            tuple(f"t{index}" for index in range(20)),
            handle,
            workload="network_topology",
        )
    )
    await asyncio.sleep(0.01)
    assert sum(item.startswith("t") for item in started) == 6

    general = asyncio.create_task(
        scheduler.execute(
            "general",
            tuple(f"g{index}" for index in range(20)),
            handle,
        )
    )
    await asyncio.sleep(0.01)

    # 已借用的拓扑目标不被抢占；普通目标使用剩余的全局槽位。
    assert scheduler.active == 10
    assert scheduler.topology_active == 6
    assert sum(item.startswith("g") for item in started) == 4

    topology_releases[0].set()
    await asyncio.sleep(0.01)

    # 普通任务存在后，拓扑动态上限恢复为基础配额 3；释放出的槽位给普通任务，
    # 不再启动新的拓扑目标。
    assert sum(item.startswith("t") for item in started) == 6
    assert sum(item.startswith("g") for item in started) == 5

    for release in topology_releases:
        release.set()
    general_release.set()
    await asyncio.gather(topology, general)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_general_capacity_is_reserved_while_topology_waits():
    scheduler = CollectionScheduler(max_in_flight=10, topology_max_in_flight=3)
    release = asyncio.Event()
    started = []

    async def handle(item):
        started.append(item)
        await release.wait()
        return item

    topology = asyncio.create_task(
        scheduler.execute(
            "topology",
            tuple(f"t{index}" for index in range(10)),
            handle,
            workload="network_topology",
        )
    )
    general = asyncio.create_task(
        scheduler.execute(
            "general",
            tuple(f"g{index}" for index in range(20)),
            handle,
        )
    )
    await asyncio.sleep(0.01)

    assert scheduler.active == 10
    assert scheduler.topology_active == 3
    assert sum(item.startswith("g") for item in started) == 7

    release.set()
    await asyncio.gather(topology, general)
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_general_workload_borrows_all_capacity_while_topology_is_idle():
    scheduler = CollectionScheduler(max_in_flight=10, topology_max_in_flight=3)
    release = asyncio.Event()
    started = []

    async def handle(item):
        started.append(item)
        await release.wait()
        return item

    run = asyncio.create_task(scheduler.execute("general", range(20), handle))
    await asyncio.sleep(0.01)

    assert scheduler.active == 10
    assert scheduler.topology_active == 0
    assert len(started) == 10

    release.set()
    await run
    await scheduler.shutdown()


@pytest.mark.asyncio
async def test_topology_arrival_does_not_preempt_running_general_targets():
    scheduler = CollectionScheduler(max_in_flight=10, topology_max_in_flight=3)
    general_releases = [asyncio.Event() for _ in range(10)]
    topology_release = asyncio.Event()
    started = []

    async def handle(item):
        started.append(item)
        if str(item).startswith("g"):
            await general_releases[int(str(item)[1:])].wait()
        else:
            await topology_release.wait()
        return item

    general = asyncio.create_task(
        scheduler.execute(
            "general",
            tuple(f"g{index}" for index in range(10)),
            handle,
        )
    )
    await asyncio.sleep(0.01)
    topology = asyncio.create_task(
        scheduler.execute(
            "topology",
            tuple(f"t{index}" for index in range(4)),
            handle,
            workload="network_topology",
        )
    )
    await asyncio.sleep(0.01)

    assert started == [f"g{index}" for index in range(10)]
    assert scheduler.topology_active == 0

    general_releases[0].set()
    await asyncio.sleep(0.01)
    assert started[-1] == "t0"
    assert scheduler.topology_active == 1

    for release in general_releases[1:]:
        release.set()
    topology_release.set()
    await asyncio.gather(general, topology)
    await scheduler.shutdown()
