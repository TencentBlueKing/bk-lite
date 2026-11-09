"""Merge ended session records with in-progress sessions from raw events.

Records are stored at session end time. A session belongs to the window when
its interval overlaps ``[from, to]``: query ``_time`` over ``[from, to + 4h15m]``,
then keep ``started_at_ms <= to``. In-progress grouping only covers
``[max(from, now-4h), to]`` and drops any session that already has a record.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.core.logger import rum_logger as logger
from apps.rum.services import logsql_stats
from apps.rum.services.victoria_client import _sessions_summary

_LIVE_LOOKBACK = timedelta(hours=4)
_RECORD_LOOKAHEAD = timedelta(hours=4, minutes=15)
_EPOCH_TTL_SECONDS = 600
_EPOCH_ABSENT = "absent"
_COUNT_FIELDS = ("viewCount", "errorCount", "actionCount", "vitalCount", "eventCount")
_TEXT_FIELDS = (
    "entryRoute",
    "userAgent",
    "geoCountry",
    "geoCity",
    "userId",
    "environment",
    "release",
    "sdkName",
    "sdkVersion",
    "trafficClass",
)


def read_session_page(query_logs, tenant_id: str, opts: dict) -> dict | None:
    """Return the merged page, or None when the window must use raw events."""

    merged = _merged_or_none(query_logs, tenant_id, opts)
    if merged is None:
        return None
    rows, truncated = merged
    if opts.get("hasError"):
        rows = [row for row in rows if int(row.get("errorCount") or 0) > 0]
    _sort_sessions(rows, opts.get("orderBy") or "impact")
    offset = _offset(opts.get("offset"))
    limit = _positive(opts.get("limit"), 200)
    summary = {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0}
    if opts.get("includeSummary", True):
        summary = _sessions_summary(rows)
    return {"sessions": rows[offset : offset + limit], "summary": summary, "truncated": truncated}


def read_session_counts(query_logs, tenant_id: str, opts: dict) -> dict[str, tuple[int, int]] | None:
    """Per-application ``(sessions, errored)`` from the merged set.

    None means the window is before the first session record, so the caller
    keeps the raw-event counts.
    """

    merged = _merged_or_none(query_logs, tenant_id, opts)
    if merged is None:
        return None
    rows, truncated = merged
    if truncated:
        # A capped merge would publish 0 for every application that did not fit.
        return None
    totals: dict[str, list[int]] = {}
    for row in rows:
        bucket = totals.setdefault(row["application"], [0, 0])
        bucket[0] += 1
        if int(row.get("errorCount") or 0) > 0:
            bucket[1] += 1
    return {app: (total, errored) for app, (total, errored) in totals.items()}


def read_session_trend(query_logs, tenant_id: str, opts: dict) -> dict | None:
    """Bucket the merged sessions. None means the raw-event trend should run.

    The raw trend ignores route, user, country, and hasError. Keep that.
    """

    trend_opts = {
        **opts,
        "hasError": False,
        "route": "",
        "userId": "",
        "country": "",
        "sessionId": "",
        "sessionIdPrefix": "",
    }
    merged = _merged_or_none(query_logs, tenant_id, trend_opts)
    if merged is None:
        return None
    rows, truncated = merged
    start = _as_utc(opts.get("from"))
    end = _as_utc(opts.get("to"))
    return {"points": _trend_points(rows, start, end), "truncated": truncated}


def _merged_or_none(query_logs, tenant_id: str, opts: dict):
    start = _as_utc(opts.get("from"))
    end = _as_utc(opts.get("to"))
    if start is None or end is None:
        return None
    now = _utcnow()
    epoch = _record_epoch(query_logs, tenant_id, now)
    if epoch is None or start < epoch:
        return None
    return _merged(query_logs, tenant_id, opts, start, end, now)


def _merged(query_logs, tenant_id: str, opts: dict, start: datetime, end: datetime, now: datetime):
    limit = logsql_stats.SESSION_GROUP_LIMIT
    # Country, route, and user are incomplete on a session record. Fetch every
    # ended session first so its raw events cannot come back through the live query.
    record_rows = query_logs(
        logsql_stats.session_record_group_query(tenant_id, _record_query_opts(opts)),
        start,
        end + _RECORD_LOOKAHEAD,
        limit,
    )
    truncated = bool(getattr(record_rows, "truncated", False))
    records = _collapse(record_rows)
    seen = {(row["application"], row["sessionId"]) for row in records}
    records = [row for row in records if _record_matches(row, opts)]
    live_from = max(start, now - _LIVE_LOOKBACK)
    live: list[dict] = []
    if live_from < end:
        live_rows = query_logs(
            logsql_stats.session_live_group_query(tenant_id, opts),
            live_from,
            end,
            limit,
        )
        truncated = truncated or bool(getattr(live_rows, "truncated", False))
        live = [row for row in _collapse(live_rows) if (row["application"], row["sessionId"]) not in seen]
    return records + live, truncated


def _record_epoch(query_logs, tenant_id: str, now: datetime) -> datetime | None:
    from django.core.cache import cache

    key = f"rum:session-end-epoch:{(tenant_id or '').strip() or 'core'}"
    cached = cache.get(key)
    if cached == _EPOCH_ABSENT:
        return None
    if isinstance(cached, str):
        parsed = logsql_stats._parse_time(cached)
        if parsed is not None:
            return parsed
    try:
        rows = query_logs(logsql_stats.session_record_epoch_query(tenant_id), None, now, 1)
    except Exception as exc:
        # The client puts the response body in the exception text. Keep the
        # traceback, replace the message, and do not touch the original error.
        safe = RuntimeError(type(exc).__name__)
        logger.warning(
            "rum session record epoch probe failed failed_stage=session_record_epoch tenant_id=%s error_type=%s",
            (tenant_id or "").strip() or "core",
            type(exc).__name__,
            exc_info=(RuntimeError, safe, exc.__traceback__),
        )
        return None
    epoch = logsql_stats._parse_time(str(rows[0].get("first_seen") or "")) if rows else None
    cache.set(key, _EPOCH_ABSENT if epoch is None else logsql_stats._fmt_dt(epoch), _EPOCH_TTL_SECONDS)
    return epoch


def _record_query_opts(opts: dict) -> dict:
    return {**opts, "country": "", "route": "", "userId": ""}


def _record_matches(row: dict, opts: dict) -> bool:
    country = (opts.get("country") or "").strip()
    if country and (row.get("geoCountry") or "") != country:
        return False
    route = (opts.get("route") or "").strip()
    if route and (row.get("entryRoute") or "") != route:
        return False
    user_id = (opts.get("userId") or "").strip()
    if user_id and (row.get("userId") or "") != user_id:
        return False
    return True


def _collapse(rows) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for raw in rows:
        item = logsql_stats.map_session_row(raw)
        if not item["sessionId"]:
            continue
        key = (item["application"], item["sessionId"])
        prev = grouped.get(key)
        if prev is None:
            grouped[key] = item
            continue
        for field in _COUNT_FIELDS:
            prev[field] = max(int(prev.get(field) or 0), int(item.get(field) or 0))
        prev["startTime"] = _earlier(prev.get("startTime"), item.get("startTime"))
        prev["endTime"] = _later(prev.get("endTime"), item.get("endTime"))
        for field in _TEXT_FIELDS:
            if not prev.get(field) and item.get(field):
                prev[field] = item[field]
    return list(grouped.values())


def _sort_sessions(rows: list[dict], order_by: str) -> None:
    order = (order_by or "impact").strip()

    def start_key(row: dict) -> str:
        return row.get("startTime") or ""

    if order == "start":
        rows.sort(key=start_key, reverse=True)
    elif order == "errors":
        rows.sort(key=lambda row: (int(row.get("errorCount") or 0), start_key(row)), reverse=True)
    elif order == "duration":
        rows.sort(key=lambda row: (_duration_ms(row), start_key(row)), reverse=True)
    else:
        rows.sort(key=lambda row: (int(row.get("errorCount") or 0), _duration_ms(row), start_key(row)), reverse=True)


def _trend_points(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
    from apps.rum.services.victoria_client import sparkline_layout

    interval, buckets = sparkline_layout(start, end)
    count = max(buckets, 1)
    step = max(60, int(interval.total_seconds()))
    totals = [0] * count
    errored = [0] * count
    origin = start.timestamp()
    for row in rows:
        begin = _parse_iso(row.get("startTime"))
        finish = _parse_iso(row.get("endTime"))
        if begin is None and finish is None:
            continue
        if begin is None:
            begin = finish
        if finish is None or finish < begin:
            finish = begin
        left = max(begin, start)
        right = min(finish, end)
        if right < left:
            continue
        first = int((left.timestamp() - origin) // step)
        last = int((right.timestamp() - origin) // step)
        if last < 0 or first >= count:
            continue
        first = max(first, 0)
        last = min(last, count - 1)
        failed = int(row.get("errorCount") or 0) > 0
        for index in range(first, last + 1):
            totals[index] += 1
            if failed:
                errored[index] += 1
    points = []
    for index in range(count):
        points.append(
            {
                "atMs": int((origin + index * step) * 1000),
                "total": totals[index],
                "errored": errored[index],
            }
        )
    return points


def _duration_ms(row: dict) -> int:
    start = _parse_iso(row.get("startTime"))
    end = _parse_iso(row.get("endTime"))
    if start is None or end is None or end < start:
        return 0
    return int((end - start).total_seconds() * 1000)


def _earlier(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if left <= right else right


def _later(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return left if left >= right else right


def _parse_iso(value: str | None) -> datetime | None:
    return logsql_stats._parse_time(value or "")


def _as_utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _offset(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _positive(value, default: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
