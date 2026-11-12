"""Merge ended session records with sessions that are still in progress.

Records are stored at session end time. A session belongs to the window when
its interval overlaps ``[from, to]``: query ``_time`` over ``[from, to + 4h15m]``,
then keep ``started_at_ms <= to``. Ended sessions are filtered, sorted, and
counted in VictoriaLogs. In-progress rows are only sessions whose last raw
event is still inside the last 30 minutes, minus any candidate that already
has a record.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.core.logger import rum_logger as logger
from apps.rum.services import logsql_stats
from apps.rum.services.victoria_client import sparkline_layout

_LIVE_LOOKBACK = timedelta(hours=4)
_LIVE_IDLE = timedelta(minutes=30)
_RECORD_LOOKAHEAD = timedelta(hours=4, minutes=15)
_EPOCH_TTL_SECONDS = 600
_EPOCH_ABSENT = "absent"
_KEY_BATCH = 100
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

    window = _window(query_logs, tenant_id, opts)
    if window is None:
        return None
    start, end, now = window
    offset = _offset(opts.get("offset"))
    limit = _positive(opts.get("limit"), 200)
    ended = _ended_page(query_logs, tenant_id, opts, start, end, offset + limit)
    live, truncated = _live_candidates(query_logs, tenant_id, opts, start, end, now)
    merged = ended + live
    _sort_sessions(merged, opts.get("orderBy") or "impact")
    summary = {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0}
    if opts.get("includeSummary", True):
        summary = _summary(query_logs, tenant_id, opts, start, end, live)
    return {"sessions": merged[offset : offset + limit], "summary": summary, "truncated": truncated}


def read_session_counts(query_logs, tenant_id: str, opts: dict) -> dict[str, tuple[int, int]] | None:
    """Per-application ``(sessions, errored)`` from record stats plus in-progress rows.

    None means the window is before the first session record, so the caller
    keeps the raw-event counts.
    """

    window = _window(query_logs, tenant_id, opts)
    if window is None:
        return None
    start, end, now = window
    totals: dict[str, list[int]] = {}
    if not _has_country(opts):
        apps = list(opts.get("applications") or [])
        rows = query_logs(
            logsql_stats.session_record_app_count_query(tenant_id, opts),
            start,
            end + _RECORD_LOOKAHEAD,
            max(len(apps), 1),
        )
        for row in rows:
            app = str(row.get("rum.application") or "")
            if not app:
                continue
            totals[app] = [int(_num(row.get("sessions"))), int(_num(row.get("errored")))]
    live, _truncated = _live_candidates(query_logs, tenant_id, opts, start, end, now)
    for row in live:
        bucket = totals.setdefault(row["application"], [0, 0])
        bucket[0] += 1
        if int(row.get("errorCount") or 0) > 0:
            bucket[1] += 1
    return {app: (total, errored) for app, (total, errored) in totals.items()}


def read_session_trend(query_logs, tenant_id: str, opts: dict) -> dict | None:
    """One point per session, in the bucket of its start. None uses the raw trend.

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
    window = _window(query_logs, tenant_id, trend_opts)
    if window is None:
        return None
    start, end, now = window
    interval, buckets = sparkline_layout(start, end)
    count = max(buckets, 1)
    step = max(60, int(interval.total_seconds()))
    origin = start.timestamp()
    points = [{"atMs": int((origin + index * step) * 1000), "total": 0, "errored": 0} for index in range(count)]
    rows = query_logs(
        logsql_stats.session_record_trend_query(tenant_id, trend_opts, int(origin * 1000), step * 1000),
        start,
        end + _RECORD_LOOKAHEAD,
        count + 2,
    )
    truncated = bool(getattr(rows, "truncated", False))
    for row in rows:
        _add_trend_bucket(points, _bucket_index(row.get("bucket")), int(_num(row.get("total"))), int(_num(row.get("errored"))))
    live, live_truncated = _live_candidates(query_logs, tenant_id, trend_opts, start, end, now)
    truncated = truncated or live_truncated
    for row in live:
        begin = _parse_iso(row.get("startTime"))
        if begin is None:
            continue
        errored = 1 if int(row.get("errorCount") or 0) > 0 else 0
        _add_trend_bucket(points, int((begin.timestamp() - origin) // step), 1, errored)
    return {"points": points, "truncated": truncated}


def _window(query_logs, tenant_id: str, opts: dict):
    start = _as_utc(opts.get("from"))
    end = _as_utc(opts.get("to"))
    if start is None or end is None:
        return None
    now = _utcnow()
    epoch = _record_epoch(query_logs, tenant_id, now)
    if epoch is None or start < epoch:
        return None
    return start, end, now


def _ended_page(query_logs, tenant_id: str, opts: dict, start: datetime, end: datetime, fetch: int) -> list[dict]:
    if _has_country(opts) or fetch <= 0:
        return []
    rows = query_logs(
        logsql_stats.session_record_page_query(tenant_id, opts, fetch),
        start,
        end + _RECORD_LOOKAHEAD,
        fetch,
    )
    ended = _collapse(rows)
    _sort_sessions(ended, opts.get("orderBy") or "impact")
    return ended[:fetch]


def _summary(query_logs, tenant_id: str, opts: dict, start: datetime, end: datetime, live: list[dict]) -> dict:
    ended_total = 0
    ended_errored = 0
    ended_median = 0
    if not _has_country(opts):
        rows = query_logs(
            logsql_stats.session_record_summary_query(tenant_id, opts),
            start,
            end + _RECORD_LOOKAHEAD,
            1,
        )
        mapped = logsql_stats.map_record_summary(rows[0] if rows else None)
        ended_total = mapped["total"]
        ended_errored = mapped["errored"]
        ended_median = mapped["medianDurationMs"]
    live_errored = sum(1 for row in live if int(row.get("errorCount") or 0) > 0)
    return {
        "total": ended_total + len(live),
        "errored": ended_errored + live_errored,
        "replayed": 0,
        "medianDurationMs": _blend_median(ended_median, ended_total, live),
    }


def _live_candidates(query_logs, tenant_id: str, opts: dict, start: datetime, end: datetime, now: datetime):
    live_from = max(start, now - _LIVE_LOOKBACK)
    active_after = now - _LIVE_IDLE
    if live_from >= end or active_after >= end:
        return [], False
    rows = query_logs(
        logsql_stats.session_live_group_query(tenant_id, opts, active_after),
        live_from,
        end,
        logsql_stats.SESSION_GROUP_LIMIT,
    )
    truncated = bool(getattr(rows, "truncated", False))
    live = _collapse(rows)
    live, probe_truncated = _drop_recorded(query_logs, tenant_id, opts, live, start, end)
    return live, truncated or probe_truncated


def _drop_recorded(query_logs, tenant_id: str, opts: dict, live: list[dict], start: datetime, end: datetime):
    keys: list[str] = []
    seen: set[str] = set()
    for row in live:
        key = row.get("sessionId") or ""
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    if not keys:
        return live, False
    apps = list(opts.get("applications") or [])
    found: set[tuple[str, str]] = set()
    truncated = False
    for batch in _chunks(keys, _KEY_BATCH):
        rows = query_logs(
            logsql_stats.session_record_present_query(tenant_id, apps, batch),
            start,
            end + _RECORD_LOOKAHEAD,
            len(batch) + 1,
        )
        truncated = truncated or bool(getattr(rows, "truncated", False))
        for raw in rows:
            key = str(raw.get("rum.session.key") or "")
            if key:
                found.add((str(raw.get("rum.application") or ""), key))
    return [row for row in live if (row["application"], row["sessionId"]) not in found], truncated


def _blend_median(ended_median: int, ended_total: int, live: list[dict]) -> int:
    """Count-weighted average of the two medians. Exact only when one side is empty."""

    live_count = len(live)
    if live_count == 0:
        return ended_median
    live_values = sorted(_duration_ms(row) for row in live)
    live_median = live_values[live_count // 2]
    if ended_total <= 0:
        return live_median
    return int((ended_median * ended_total + live_median * live_count) / (ended_total + live_count))


def _add_trend_bucket(points: list[dict], index: int, total: int, errored: int) -> None:
    if index < 0 or not points:
        return
    if index >= len(points):
        index = len(points) - 1
    points[index]["total"] += total
    points[index]["errored"] += errored


def _bucket_index(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return -1


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _has_country(opts: dict) -> bool:
    return bool((opts.get("country") or "").strip())


def _chunks(items: list[str], size: int):
    step = max(1, size)
    for start in range(0, len(items), step):
        yield items[start : start + step]


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
