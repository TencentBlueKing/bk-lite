from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# Explicit from/to windows are capped so one request cannot make VictoriaLogs
# scan an unbounded time span. 31 days covers the longest named range (7d)
# and the collector's 14-day age gate with headroom.
MAX_RANGE_SPAN = timedelta(days=31)


def parse_range_params(params: dict[str, Any]) -> tuple[datetime, datetime]:
    """Parse RUM range / from / to query params (UTC)."""
    now = datetime.now(timezone.utc)
    raw_from = params.get("from")
    raw_to = params.get("to")
    if raw_from is not None and raw_to is not None and str(raw_from) and str(raw_to):
        try:
            start = datetime.fromtimestamp(int(raw_from) / 1000.0, tz=timezone.utc)
            end = datetime.fromtimestamp(int(raw_to) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            raise ValueError("invalid from/to") from exc
        if start >= end:
            raise ValueError("from must be before to")
        if end - start > MAX_RANGE_SPAN:
            raise ValueError("from/to span exceeds the maximum of 31 days")
        return start, end

    key = (params.get("range") or "24h").strip() or "24h"
    windows = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    if key not in windows:
        raise ValueError("invalid range")
    return now - windows[key], now


def empty_session_list(*, reason: str | None = None) -> dict:
    page = {
        "sessions": [],
        "summary": {
            "total": 0,
            "errored": 0,
            "replayed": 0,
            "medianDurationMs": 0,
        },
    }
    return _degrade(page, reason)


def empty_session_journey(*, reason: str | None = None) -> dict:
    page = {
        "session": {},
        "views": [],
        "actions": [],
        "errors": [],
        "vitals": [],
        "network": [],
        "console": [],
    }
    return _degrade(page, reason)


def empty_session_trend(*, reason: str | None = None) -> dict:
    return _degrade({"points": []}, reason)


def empty_replay_manifest(*, reason: str | None = None) -> dict:
    return _degrade({"state": "unavailable", "retentionDays": 0, "recordings": []}, reason)


def empty_view_list(*, mode: str = "route", reason: str | None = None) -> dict:
    return _degrade(
        {
            "mode": mode or "route",
            "summary": {"lcpP75": 0, "inpP75": 0, "clsP75": 0},
            "releases": [],
            "rows": [],
        },
        reason,
    )


def empty_error_list(*, reason: str | None = None) -> dict:
    return _degrade({"issues": []}, reason)


def empty_error_detail(*, reason: str | None = None) -> dict:
    return _degrade({"fingerprint": "", "occurrences": [], "signals": []}, reason)


def empty_release_list(*, reason: str | None = None) -> dict:
    return _degrade({"releases": []}, reason)


def apply_degradation(page: dict, reason: str | None) -> dict:
    """Attach exclusive pipeline flags (PipelineDegradation.Degrade)."""

    if reason == "control":
        page["controlUnavailable"] = True
        page.pop("analyticsUnavailable", None)
    elif reason == "analytics":
        page["analyticsUnavailable"] = True
        page.pop("controlUnavailable", None)
    return page


def _degrade(page: dict, reason: str | None) -> dict:
    return apply_degradation(page, reason)
