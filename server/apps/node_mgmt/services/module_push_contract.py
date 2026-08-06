from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

LINK_CONFLICT = "link_conflict"
EVENT_UPSERT = "upsert"
EVENT_LIFECYCLE = "lifecycle"

REQUIRED = ("source_module", "source_id", "event_type", "occurred_at", "raw")


@dataclass
class IngestEnvelope:
    source_module: str
    source_id: str
    event_type: str
    occurred_at: str
    raw: dict[str, Any]
    link_ids: dict[str, Any] = field(default_factory=dict)
    causation_id: str | None = None


@dataclass
class IngestResult:
    id: str | int | None
    created: bool = False
    updated: bool = False
    ignored: bool = False
    conflict: str | None = None
    claimed: bool = False  # 存量认领

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PushTargetStatus:
    state: str
    error: str | None = None
    attempts: int = 0


def validate_envelope(data: dict[str, Any]) -> tuple[bool, str | None]:
    if not isinstance(data, dict):
        return False, "envelope must be a dict"
    for key in REQUIRED:
        if key not in data or data[key] in (None, ""):
            return False, f"{key} is required"
    if not isinstance(data.get("raw"), dict):
        return False, "raw must be an object"
    link_ids = data.get("link_ids") or {}
    if not isinstance(link_ids, dict):
        return False, "link_ids must be an object"
    return True, None
