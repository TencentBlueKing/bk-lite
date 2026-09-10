from dataclasses import dataclass, field
from typing import Dict, List

REASON_CODES = frozenset(
    {
        "success",
        "cache_hit",
        "not_found",
        "team_mismatch",
        "rule_unmatched",
        "missing_binding",
        "provider_failed",
        "circuit_open",
        "budget_exhausted",
        "inflight_coalesced",
        "provider_saturated",
        "projection_empty",
        "conflict",
    }
)


@dataclass
class RuleOutcome:
    rule_id: int | None
    namespace: str
    status: str
    count: int = 1

    def __post_init__(self):
        if self.status not in REASON_CODES:
            raise ValueError(f"未知的丰富结果原因码: {self.status}")


@dataclass
class EnrichmentSummary:
    received: int = 0
    enriched: int = 0
    not_found: int = 0
    failed: int = 0
    circuit_open: int = 0
    budget_exhausted: int = 0
    inflight_coalesced: int = 0
    provider_saturated: int = 0
    conflict: int = 0
    duration_ms: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {name: int(value) for name, value in vars(self).items()}


@dataclass
class EnrichmentBatchResult:
    events: List[dict]
    summary: EnrichmentSummary
    outcomes: List[RuleOutcome] = field(default_factory=list)
