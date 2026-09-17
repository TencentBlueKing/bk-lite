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
    # 扫描带凭据重复推送：目标已有 cmdb_id+采集时返回；node_mgmt/无凭据路径不使用。
    skipped: bool = False

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


def ingest_auth_kwargs(actor_scope: dict[str, Any] | None) -> dict[str, Any]:
    """跨模块 ingest 的授权字段：有 user_info 才带上，供对端与报文组织取交集。"""
    scope = actor_scope or {}
    kwargs: dict[str, Any] = {
        "allowed_org_ids": list(scope.get("allowed_org_ids") or []),
        "operator": str(scope.get("operator") or ""),
    }
    user_info = scope.get("user_info")
    if isinstance(user_info, dict) and user_info:
        kwargs["user_info"] = user_info
    return kwargs
