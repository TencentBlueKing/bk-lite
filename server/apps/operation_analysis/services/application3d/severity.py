from __future__ import annotations

from apps.operation_analysis.services.application3d.constants import MONITOR_LEVEL_TO_SEVERITY_ID, SEVERITY_TABLE


def severity_from_monitor_level(level: str | None) -> dict | None:
    """Normalize Monitor alert level into canonical Severity; unknown levels → None."""
    if not level:
        return None
    severity_id = MONITOR_LEVEL_TO_SEVERITY_ID.get(str(level).strip().lower())
    if not severity_id:
        return None
    return dict(SEVERITY_TABLE[severity_id])


def empty_severity_counts() -> dict[str, int]:
    return {"critical": 0, "error": 0, "warning": 0, "info": 0}


def normal_severity() -> dict:
    return dict(SEVERITY_TABLE["normal"])
