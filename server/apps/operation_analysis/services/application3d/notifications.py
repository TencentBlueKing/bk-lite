from __future__ import annotations

from typing import Any, Iterable


def summarize_notification(
    *,
    policy_notice_configured: bool,
    notice_logs: Iterable[dict[str, Any]] | None,
) -> dict[str, Any]:
    """
    Build NotificationSummary from MonitorPolicy.notice + MonitorAlert.notice_logs.

    Ignores alert_center_notified and recipient/channel identity details.
    """
    if not policy_notice_configured:
        return {"configured": False, "state": "not_configured"}

    logs = [entry for entry in (notice_logs or []) if isinstance(entry, dict) and not entry.get("is_alert_center")]
    if not logs:
        return {"configured": True, "state": "pending"}

    successes = [entry for entry in logs if entry.get("success") is True]
    failures = [entry for entry in logs if entry.get("success") is False]
    unknown = [entry for entry in logs if entry.get("success") is not True and entry.get("success") is not False]

    if unknown and not successes and not failures:
        return {"configured": True, "state": "unknown"}
    if successes and failures:
        return {"configured": True, "state": "partially_delivered"}
    if successes and not failures:
        return {"configured": True, "state": "delivered"}
    if failures and not successes:
        return {"configured": True, "state": "failed"}
    if not successes and not failures:
        return {"configured": True, "state": "pending"}
    return {"configured": True, "state": "unknown"}
