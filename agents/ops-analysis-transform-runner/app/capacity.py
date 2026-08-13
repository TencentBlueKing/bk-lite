"""In-process org concurrency gate for a single Runner replica."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager


class CapacityError(Exception):
    def __init__(self, message: str = "组织转换并发已满", *, code: str = "transform_capacity_exceeded"):
        super().__init__(message)
        self.code = code


class OrgConcurrencyLimiter:
    def __init__(self, limit: int = 3):
        self.limit = max(1, int(limit))
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}

    @contextmanager
    def acquire(self, org_key: str, *, timeout: float = 0.0):
        key = str(org_key or "default")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                current = self._counts.get(key, 0)
                if current < self.limit:
                    self._counts[key] = current + 1
                    break
            if time.monotonic() >= deadline:
                raise CapacityError()
            time.sleep(0.01)
        try:
            yield
        finally:
            with self._lock:
                current = self._counts.get(key, 0) - 1
                if current <= 0:
                    self._counts.pop(key, None)
                else:
                    self._counts[key] = current
