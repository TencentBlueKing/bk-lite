"""进程内采集指标；由健康接口导出，避免引入额外运行时依赖。"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class CollectionMetrics:
    def __init__(
        self,
        *,
        sample_capacity: int = 500,
        sample_window_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if sample_capacity <= 0:
            raise ValueError("sample_capacity must be greater than zero")
        if sample_window_seconds <= 0:
            raise ValueError("sample_window_seconds must be greater than zero")
        self._counters: dict[str, float] = {
            "preflight_duration_seconds_total": 0.0,
            "preflight_total": 0,
            "target_unreachable_total": 0,
            "credential_attempt_total": 0,
            "credential_cooldown_total": 0,
            "access_probe_duration_seconds_total": 0.0,
            "access_probe_total": 0,
            "access_probe_timeout_total": 0,
            "access_probe_error_total": 0,
            "plugin_duration_seconds_total": 0.0,
            "plugin_total": 0,
            "plugin_timeout_total": 0,
            "result_publish_failure_total": 0,
            "lease_takeover_total": 0,
            "credential_state_redis_error_total": 0,
            "target_execution_error_total": 0,
            "preflight_timeout_total": 0,
            "probe_timeout_total": 0,
            "collection_timeout_total": 0,
            "publish_timeout_total": 0,
            "publish_lines_total": 0,
            "publish_bytes_total": 0,
            "snmp_timeout_clamped_total": 0,
            "scheduler_dispatch_total": 0,
            "scheduler_yield_total": 0,
            "run_preparation_fallback_total": 0,
        }
        self._sample_capacity = int(sample_capacity)
        self._sample_window_seconds = float(sample_window_seconds)
        self._monotonic = monotonic
        self._samples: dict[str, deque[tuple[float, float]]] = {}
        self._gauges: dict[str, float] = {"sync_calls_in_flight": 0}

    def increment(self, name: str, value: float = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def observe(self, name: str, value: float) -> None:
        samples = self._samples.get(name)
        if samples is None:
            samples = deque(maxlen=self._sample_capacity)
            self._samples[name] = samples
        now = self._monotonic()
        samples.append((now, float(value)))
        self._prune(samples, now)

    def add_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = max(0.0, self._gauges.get(name, 0.0) + float(value))

    def snapshot(self) -> dict[str, float]:
        snapshot = dict(self._counters)
        snapshot.update(self._gauges)
        now = self._monotonic()
        for name, samples in self._samples.items():
            self._prune(samples, now)
            ordered = sorted(value for _observed_at, value in samples)
            snapshot[f"{name}_p95"] = _percentile(ordered, 0.95)
            snapshot[f"{name}_p99"] = _percentile(ordered, 0.99)
        return snapshot

    def _prune(self, samples: deque[tuple[float, float]], now: float) -> None:
        cutoff = now - self._sample_window_seconds
        while samples and samples[0][0] < cutoff:
            samples.popleft()


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    index = int((len(ordered) - 1) * fraction)
    return ordered[index]
