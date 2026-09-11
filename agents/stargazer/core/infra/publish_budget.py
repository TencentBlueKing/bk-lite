"""单目标累计发送预算：仅统计至少一条消息正在发送/等待 ACK 的时间。"""

from __future__ import annotations

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
            yield time.monotonic() + self.remaining
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
