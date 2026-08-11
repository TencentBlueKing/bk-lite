"""轻量事件循环延迟采样器。"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class EventLoopLagMonitor:
    def __init__(self, *, interval_seconds: float = 1.0) -> None:
        self._interval = interval_seconds
        self._samples: deque[float] = deque(maxlen=300)
        self._task: asyncio.Task | None = None

    @property
    def latest_seconds(self) -> float:
        return self._samples[-1] if self._samples else 0.0

    @property
    def p99_seconds(self) -> float:
        if not self._samples:
            return 0.0
        ordered = sorted(self._samples)
        index = min(len(ordered) - 1, int(len(ordered) * 0.99))
        return ordered[index]

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="collection-event-loop-lag"
            )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        expected = time.monotonic() + self._interval
        while True:
            await asyncio.sleep(self._interval)
            now = time.monotonic()
            self._samples.append(max(0.0, now - expected))
            expected = now + self._interval
