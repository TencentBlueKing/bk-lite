"""单目标累计发送预算：仅统计至少一条消息正在发送/等待 ACK 的时间。"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager


class PublishBudget:
    """由事件循环持有；并行消息共享活动区间，不重复扣时，空闲区间暂停。"""

    def __init__(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("publish budget must be greater than zero")
        self.seconds = float(seconds)
        self._elapsed = 0.0
        self._active = 0
        self._started = 0.0
        self.credit_wait_seconds = 0.0
        # 单结果的有界诊断计数，不保留消息、凭据或逐分片明细。
        self.total_lines: int | None = None
        self.total_bytes: int | None = None
        self.attempted_lines = 0
        self.confirmed_lines = 0
        self.retry_count = 0
        self.slowest_attempt_seconds = 0.0

    @property
    def elapsed(self) -> float:
        return self._elapsed + (time.monotonic() - self._started if self._active else 0.0)

    @property
    def remaining(self) -> float:
        return max(0.0, self.seconds - self.elapsed)

    @contextmanager
    def sending(self):
        if not self._active:
            self._started = time.monotonic()
        self._active += 1
        try:
            # 活跃区间中的全部消息获得同一个截止点；重试、后续 chunk 只获剩余量。
            # asyncio 的绝对截止点必须使用 loop.time()，不能假定它与 monotonic 同源。
            yield asyncio.get_running_loop().time() + self.remaining
        finally:
            self._active -= 1
            if not self._active:
                self._elapsed += time.monotonic() - self._started

    @contextmanager
    def waiting_for_credit(self):
        started = time.monotonic()
        try:
            yield
        finally:
            self.credit_wait_seconds += time.monotonic() - started
