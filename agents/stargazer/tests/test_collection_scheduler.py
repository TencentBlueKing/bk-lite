import asyncio

import pytest
from core.collection.scheduler import CollectionScheduler


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
