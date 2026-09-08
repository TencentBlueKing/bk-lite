from dataclasses import dataclass
from time import monotonic
from uuid import uuid4


@dataclass(frozen=True)
class CircuitDecision:
    allowed: bool
    is_probe: bool = False
    permit: str = ""


class CircuitBreaker:
    """共享缓存支撑的 Provider 熔断状态机。open 请求不会续期。"""

    def __init__(
        self,
        *,
        cache_backend,
        clock=monotonic,
        failure_threshold: int = 2,
        open_seconds: int = 30,
        failure_window_seconds: int = 60,
        probe_lease_seconds: int = 5,
    ):
        self.cache = cache_backend
        self.clock = clock
        self.failure_threshold = max(1, failure_threshold)
        self.open_seconds = max(1, open_seconds)
        self.failure_window_seconds = max(self.open_seconds, failure_window_seconds)
        self.probe_lease_seconds = max(1, probe_lease_seconds)

    @staticmethod
    def _failure_key(scope_key: str) -> str:
        return f"{scope_key}:failures"

    @staticmethod
    def _probe_key(scope_key: str, retry_at: float) -> str:
        return f"{scope_key}:probe:{int(retry_at * 1000)}"

    def before_call(self, scope_key: str) -> CircuitDecision:
        state = self.cache.get(scope_key) or {}
        if state.get("status") != "open":
            return CircuitDecision(allowed=True)

        retry_at = float(state.get("retry_at") or 0)
        if self.clock() < retry_at:
            return CircuitDecision(allowed=False)

        permit = uuid4().hex
        acquired = self.cache.add(
            self._probe_key(scope_key, retry_at),
            permit,
            timeout=self.probe_lease_seconds,
        )
        return CircuitDecision(allowed=bool(acquired), is_probe=bool(acquired), permit=permit if acquired else "")

    def after_call(self, scope_key: str, decision: CircuitDecision, *, success: bool) -> str | None:
        if not decision.allowed:
            return None
        failure_key = self._failure_key(scope_key)
        if success:
            self.cache.delete(scope_key)
            self.cache.delete(failure_key)
            return "closed" if decision.is_probe else None

        if decision.is_probe:
            failures = self.failure_threshold
        else:
            self.cache.add(failure_key, 0, timeout=self.failure_window_seconds)
            try:
                failures = self.cache.incr(failure_key)
            except ValueError:
                # DummyCache 等不保存 add 的后端不支持该原子序列；降级为一次失败，
                # 生产 Redis/Memcached 仍走原子 incr。
                failures = 1
                self.cache.set(failure_key, failures, timeout=self.failure_window_seconds)
        if failures < self.failure_threshold:
            return None

        self.cache.set(
            scope_key,
            {
                "status": "open",
                "retry_at": self.clock() + self.open_seconds,
            },
            timeout=self.open_seconds + self.failure_window_seconds,
        )
        self.cache.delete(failure_key)
        return "open"
