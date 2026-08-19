"""周期输出全局异步目标槽位与发布背压使用情况。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping

from core.logger import logger


class CapacityUsageReporter:
    def __init__(
        self,
        *,
        snapshot: Callable[[], Mapping[str, float | int]],
        emit: Callable[[dict[str, float | int]], None],
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self._snapshot = snapshot
        self._emit = emit
        self._interval_seconds = float(interval_seconds)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run(), name="collection-capacity-reporter"
            )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            try:
                self._emit(with_capacity_utilization(self._snapshot()))
            except Exception:  # noqa: BLE001 - 观测失败不得终止采集运行时
                logger.exception("event=collection_capacity_log_failed")
            await asyncio.sleep(self._interval_seconds)


def with_capacity_utilization(
    snapshot: Mapping[str, float | int]
) -> dict[str, float | int]:
    result = dict(snapshot)
    target_capacity = max(0, int(result.get("target_slots_capacity", 0)))
    target_used = max(0, int(result.get("target_slots_used", 0)))
    queue_capacity = max(0, int(result.get("publish_queue_capacity", 0)))
    queue_depth = max(0, int(result.get("publish_queue_depth", 0)))
    result["target_slots_available"] = (
        max(0, target_capacity - target_used) if target_capacity else 0
    )
    result["target_slots_utilization_percent"] = (
        round(target_used * 100 / target_capacity, 2) if target_capacity else 0.0
    )
    result["publish_queue_utilization_percent"] = (
        round(queue_depth * 100 / queue_capacity, 2) if queue_capacity else 0.0
    )
    return result
