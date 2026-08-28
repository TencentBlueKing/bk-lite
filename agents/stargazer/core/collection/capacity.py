"""目标执行容量与活动计数原语。"""

from __future__ import annotations

import asyncio


class TargetActivityTracker:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def enter(self) -> None:
        async with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    async def exit(self) -> None:
        async with self._lock:
            self.active = max(0, self.active - 1)


class TargetWorkerBudget:
    """跨运行限制已创建且未完成的目标 worker 协程数量。

    capacity=0 表示不限制（按 desired 全量发放）。
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 0:
            raise ValueError("capacity must be >= 0 (0 means unlimited)")
        self._unlimited = capacity == 0
        self._capacity = capacity
        self._available = 0 if self._unlimited else capacity
        self._condition = asyncio.Condition()
        self.active = 0
        self.peak = 0

    async def reserve(self, desired: int) -> int:
        async with self._condition:
            wanted = max(1, desired)
            if self._unlimited:
                self.active += wanted
                self.peak = max(self.peak, self.active)
                return wanted
            while self._available <= 0:
                await self._condition.wait()
            reserved = min(wanted, self._available)
            self._available -= reserved
            self.active += reserved
            self.peak = max(self.peak, self.active)
            return reserved

    async def release(self, count: int) -> None:
        async with self._condition:
            released = min(max(0, count), self.active)
            self.active -= released
            if not self._unlimited:
                self._available = min(self._capacity, self._available + released)
            self._condition.notify_all()


class _UnlimitedTargetGate:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def unlimited_target_gate() -> _UnlimitedTargetGate:
    return _UnlimitedTargetGate()
