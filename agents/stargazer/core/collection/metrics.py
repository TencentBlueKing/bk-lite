"""进程内采集指标；由健康接口导出，避免引入额外运行时依赖。"""

from __future__ import annotations


class CollectionMetrics:
    def __init__(self) -> None:
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
        }

    def increment(self, name: str, value: float = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def snapshot(self) -> dict[str, float]:
        return dict(self._counters)
