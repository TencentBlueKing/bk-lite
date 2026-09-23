"""InterruptWatch：按时间轮询中断，不按 SSE 帧次数查库。"""

from __future__ import annotations

import asyncio
import time

import pytest

from apps.opspilot.utils.execution_interrupt import InterruptWatch


@pytest.mark.asyncio
async def test_interrupt_watch_poll_count_independent_of_event_reads():
    """慢 checker 时，多次 is_interrupted 读不应触发同等次数的查库。"""
    checks = 0

    async def slow_checker(_execution_id: str) -> bool:
        nonlocal checks
        checks += 1
        await asyncio.sleep(0.05)
        return False

    watch = InterruptWatch(
        "exec-watch-1",
        interval_seconds=10.0,
        checker=slow_checker,
    )
    await watch.start()
    try:
        t0 = time.perf_counter()
        for _ in range(100):
            assert watch.is_interrupted() is False
        elapsed = time.perf_counter() - t0
    finally:
        await watch.aclose()

    # 仅启动时查一次；100 次读标志不应再查库
    assert checks == 1
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_interrupt_watch_sets_flag_when_checker_returns_true():
    async def yes(_execution_id: str) -> bool:
        return True

    watch = InterruptWatch("exec-watch-2", interval_seconds=10.0, checker=yes)
    await watch.start()
    try:
        assert watch.is_interrupted() is True
    finally:
        await watch.aclose()


@pytest.mark.asyncio
async def test_interrupt_watch_no_execution_id_never_checks():
    checks = 0

    async def boom(_execution_id: str) -> bool:
        nonlocal checks
        checks += 1
        return False

    watch = InterruptWatch("", interval_seconds=0.01, checker=boom)
    await watch.start()
    try:
        assert watch.is_interrupted() is False
        await asyncio.sleep(0.05)
    finally:
        await watch.aclose()
    assert checks == 0
