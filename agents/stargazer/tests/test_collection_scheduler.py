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
async def test_three_thousand_targets_remain_bounded_by_two_hundred_window():
    scheduler = CollectionScheduler(max_in_flight=200)
    release = asyncio.Event()

    async def handle(item):
        await release.wait()
        return item

    run = asyncio.create_task(scheduler.execute("three-thousand", range(3000), handle))
    await asyncio.sleep(0.05)

    assert scheduler.active == 200
    assert scheduler.peak == 200

    release.set()
    results = await run
    assert len(results) == 3000
    assert results[0] == 0
    assert results[-1] == 2999
    await scheduler.shutdown()
