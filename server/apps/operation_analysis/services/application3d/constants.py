"""application3D domain constants and wire-facing enums."""

from __future__ import annotations

# Soft safety budget only — not product hard capacity until Phase 7 benchmark.
APPLICATION3D_SAFETY_MAX_APPLICATIONS = 500
APPLICATION3D_RELATION_BATCH_SIZE = 100
APPLICATION3D_ENTITY_BATCH_SIZE = 100
APPLICATION3D_ALARM_PAGE_SIZE = 20

APPLICATION_RUN_HOST_ASST = "application_run_host"
SYSTEM_CONTAINS_APPLICATION_ASST = "system_contains_application"

FILTER_SYSTEM_STATUS = "system_status"

PROPERTY_ALLOWLIST: tuple[str, ...] = (
    "app_id",
    "app_type",
    "organization",
    "operator",
    "bak_operator",
    "comment",
)

SEVERITY_TABLE: dict[str, dict] = {
    "critical": {
        "id": "critical",
        "label": "严重",  # Align Monitor product: monitor.events.critical
        "rank": 400,
        "color": "critical",
    },
    "error": {
        "id": "error",
        "label": "错误",
        "rank": 300,
        "color": "danger",
    },
    "warning": {
        "id": "warning",
        "label": "警告",
        "rank": 200,
        "color": "warning",
    },
    "info": {
        "id": "info",
        "label": "提示",
        "rank": 100,
        "color": "info",
    },
    "normal": {
        "id": "normal",
        "label": "正常",
        "rank": 0,
        "color": "success",
    },
}

MONITOR_LEVEL_TO_SEVERITY_ID = {
    "critical": "critical",
    "error": "error",
    "warning": "warning",
    "info": "info",
}
