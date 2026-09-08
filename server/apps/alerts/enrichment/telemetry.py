from typing import Dict

from django.core.cache import cache

METRIC_TTL_SECONDS = 7 * 24 * 60 * 60
KNOWN_PROVIDERS = ("cmdb",)
SUMMARY_FIELDS = (
    "received",
    "enriched",
    "not_found",
    "failed",
    "circuit_open",
    "budget_exhausted",
    "inflight_coalesced",
    "provider_saturated",
    "conflict",
    "duration_ms",
)


class EnrichmentTelemetry:
    """低基数缓存计数器；遥测失败不得影响告警接入。"""

    PREFIX = "alerts:enrichment:runtime"

    def __init__(self, cache_backend=None):
        self.cache = cache_backend if cache_backend is not None else cache

    def _increment(self, key: str, amount: int = 1) -> None:
        if not amount:
            return
        self.cache.add(key, 0, timeout=METRIC_TTL_SECONDS)
        try:
            self.cache.incr(key, int(amount))
        except ValueError:
            self.cache.set(key, int(amount), timeout=METRIC_TTL_SECONDS)

    def record(self, summary) -> None:
        self._increment(f"{self.PREFIX}:batch_total")
        for field in SUMMARY_FIELDS:
            self._increment(f"{self.PREFIX}:summary:{field}", getattr(summary, field, 0))

    def record_provider(self, provider_type: str, status: str, duration_ms: int, count: int) -> None:
        self._increment(f"{self.PREFIX}:provider:{provider_type}:attempt:{status}", count)
        self._increment(f"{self.PREFIX}:provider:{provider_type}:duration_ms", duration_ms)

    def record_cache(self, provider_type: str, result: str, count: int = 1) -> None:
        self._increment(f"{self.PREFIX}:provider:{provider_type}:cache:{result}", count)

    def record_circuit_transition(self, provider_type: str, to_state: str) -> None:
        self._increment(f"{self.PREFIX}:provider:{provider_type}:circuit:{to_state}")


def read_runtime_metrics(cache_backend=None) -> Dict:
    backend = cache_backend if cache_backend is not None else cache

    def value(key):
        try:
            return int(backend.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    summary = {field: value(f"{EnrichmentTelemetry.PREFIX}:summary:{field}") for field in SUMMARY_FIELDS}
    providers = {}
    for provider_type in KNOWN_PROVIDERS:
        providers[provider_type] = {
            "attempt": {
                status: value(f"{EnrichmentTelemetry.PREFIX}:provider:{provider_type}:attempt:{status}")
                for status in ("success", "failed", "circuit_open", "budget_exhausted", "provider_saturated")
            },
            "cache": {
                result: value(f"{EnrichmentTelemetry.PREFIX}:provider:{provider_type}:cache:{result}")
                for result in ("hit", "miss", "negative_hit", "inflight_coalesced")
            },
            "duration_ms": value(f"{EnrichmentTelemetry.PREFIX}:provider:{provider_type}:duration_ms"),
            "circuit_transition": {
                state: value(f"{EnrichmentTelemetry.PREFIX}:provider:{provider_type}:circuit:{state}") for state in ("open", "closed")
            },
        }
    return {
        "batch_total": value(f"{EnrichmentTelemetry.PREFIX}:batch_total"),
        "summary": summary,
        "providers": providers,
    }
