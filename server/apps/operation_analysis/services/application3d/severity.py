from __future__ import annotations

from apps.operation_analysis.services.application3d.constants import MONITOR_LEVEL_TO_SEVERITY_ID, SEVERITY_TABLE


def severity_from_monitor_level(level: str | None) -> dict | None:
    """Normalize Monitor alert level into canonical Severity.

    Empty / blank level is treated as warning (aligns with Monitor
    `no_data_level or "warning"`). Non-empty unmapped values → None.
    """
    normalized = str(level or "").strip().lower()
    if not normalized:
        return dict(SEVERITY_TABLE["warning"])
    severity_id = MONITOR_LEVEL_TO_SEVERITY_ID.get(normalized)
    if not severity_id:
        return None
    return dict(SEVERITY_TABLE[severity_id])


def empty_severity_counts() -> dict[str, int]:
    return {"critical": 0, "error": 0, "warning": 0, "info": 0}


def normal_severity() -> dict:
    return dict(SEVERITY_TABLE["normal"])
