from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.rum.services import logsql_stats
from apps.rum.services.victoria_client import (
    VictoriaClient,
    funnel_reached,
    health_from_events,
    parse_event,
    rum_apps_filter,
    sparkline_layout,
)

# Align with web/src/app/rum/lib/cwv.ts good / needs-improvement upper bounds.
_CWV_BOUNDS = {
    "lcp": (2500.0, 4000.0),
    "inp": (200.0, 500.0),
    "cls": (0.1, 0.25),
}


def _cwv_bucket(metric: str, value: float) -> str:
    bounds = _CWV_BOUNDS.get(metric)
    if not bounds or value <= 0:
        return "missing"
    good, poor = bounds
    if value <= good:
        return "good"
    if value <= poor:
        return "needsImprove"
    return "poor"


def _ua_is_mobile(ua: str) -> bool:
    text = ua or ""
    if "iPad" in text or "Tablet" in text or "PlayBook" in text:
        return False
    return bool("Mobile" in text or "Android" in text or "iPhone" in text or "iPod" in text or "Windows Phone" in text)


class VictoriaAnalytics:
    """Analytics over VictoriaLogs LogsQL."""

    def __init__(self, client: VictoriaClient):
        self.client = client

    @classmethod
    def open(
        cls,
        *,
        logs_endpoint: str,
        traces_endpoint: str,
        account_id: int = 0,
        project_id: int = 0,
        timeout_seconds: float = 15.0,
        ping: bool = True,
    ) -> VictoriaAnalytics:
        client = VictoriaClient(
            logs_endpoint=logs_endpoint,
            traces_endpoint=traces_endpoint,
            account_id=account_id,
            project_id=project_id,
            timeout_seconds=timeout_seconds,
        )
        if ping:
            client.ping()
        return cls(client)

    def available(self) -> bool:
        return self.client is not None

    def _tenant(self, tenant_id: str) -> str:
        return (tenant_id or "").strip() or "core"

    def _load_events(
        self,
        tenant_id: str,
        apps: list[str],
        start: datetime,
        end: datetime,
        extra: str = "",
        limit: int = 5000,
    ) -> list[dict]:
        if limit <= 0:
            limit = 5000
        if not apps:
            # No enabled/requested application: nothing to read. Never fall back
            # to a tenant-wide query.
            return []
        query = rum_apps_filter(self._tenant(tenant_id), apps)
        if extra:
            query = f"{query} {extra}"
        rows = self.client.query_logs(query, start, end, limit)
        return [parse_event(row) for row in rows]

    def applications_page(self, tenant_id: str, start: datetime, end: datetime, enabled_apps: list[str]) -> tuple[list[dict], dict[str, list[float]]]:
        events = self._load_events(tenant_id, enabled_apps, start, end, limit=8000)
        _, buckets = sparkline_layout(start, end)
        return health_from_events(events, enabled_apps, start, end, buckets)

    def application_overview(self, tenant_id: str, application: str, start: datetime, end: datetime) -> dict:
        rows, sparks = self.applications_page(tenant_id, start, end, [application])
        kpi = rows[0] if rows else {"application": application}
        trend = self.session_trend(
            tenant_id,
            {
                "from": start,
                "to": end,
                "applications": [application],
                "traffic": "all",
            },
        )
        events = self._load_events(tenant_id, [application], start, end, limit=8000)
        countries: dict[str, dict] = {}
        envs: dict[str, dict] = {}
        releases: dict[str, dict] = {}
        country_sessions: dict[str, set[str]] = {}
        env_sessions: dict[str, set[str]] = {}
        rel_sessions: dict[str, set[str]] = {}
        mobile_sessions: set[str] = set()
        desktop_sessions: set[str] = set()
        for event in events:
            session_id = event.get("sessionId") or ""
            if event.get("eventType") == "view":
                country = event.get("country") or ""
                countries.setdefault(country, {"country": country, "views": 0, "sessions": 0})
                countries[country]["views"] += 1
                country_sessions.setdefault(country, set()).add(session_id)
            ua = (event.get("userAgent") or "").lower()
            if session_id and ua:
                if "mobile" in ua or "android" in ua:
                    mobile_sessions.add(session_id)
                else:
                    desktop_sessions.add(session_id)
            if event.get("environment"):
                key = event["environment"]
                envs.setdefault(key, {"key": key, "views": 0, "sessions": 0})
                if event.get("eventType") == "view":
                    envs[key]["views"] += 1
                env_sessions.setdefault(key, set()).add(event.get("sessionId") or "")
            if event.get("release"):
                key = event["release"]
                releases.setdefault(key, {"key": key, "views": 0, "sessions": 0})
                if event.get("eventType") == "view":
                    releases[key]["views"] += 1
                rel_sessions.setdefault(key, set()).add(event.get("sessionId") or "")
        for key, row in countries.items():
            row["sessions"] = len({sid for sid in country_sessions.get(key, set()) if sid})
        for key, row in envs.items():
            row["sessions"] = len({sid for sid in env_sessions.get(key, set()) if sid})
        for key, row in releases.items():
            row["sessions"] = len({sid for sid in rel_sessions.get(key, set()) if sid})
        # 同一会话只要出现过移动端标识，就只计入移动端，避免一次访问被两边各算一台。
        desktop_sessions -= mobile_sessions
        devices = {"mobile": len(mobile_sessions), "desktop": len(desktop_sessions)}
        return {
            "application": application,
            "kpi": kpi,
            "sparkline": sparks.get(application) or [],
            "trend": trend.get("points") or [],
            "countries": list(countries.values()),
            "devices": devices,
            "environments": list(envs.values()),
            "releases": list(releases.values()),
        }

    def list_sessions(self, tenant_id: str, opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        if not apps:
            return {
                "sessions": [],
                "summary": {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0},
                "truncated": False,
            }
        page_limit = int(opts.get("limit") or 0) or 200
        page = self._stats(
            tenant_id,
            logsql_stats.session_page_query(self._tenant(tenant_id), opts),
            opts,
            limit=page_limit,
        )
        sessions = []
        for row in page:
            item = logsql_stats.map_session_row(row)
            if item["sessionId"]:
                sessions.append(item)
        summary = {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0}
        truncated = bool(getattr(page, "truncated", False))
        if opts.get("includeSummary", True):
            summary_rows = self._stats(tenant_id, logsql_stats.session_summary_query(self._tenant(tenant_id), opts), opts)
            summary = logsql_stats.map_session_summary(summary_rows[0] if summary_rows else None)
            truncated = truncated or bool(getattr(summary_rows, "truncated", False))
        return {"sessions": sessions, "summary": summary, "truncated": truncated}

    def session_trend(self, tenant_id: str, opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        if not apps:
            return {"points": []}
        interval, buckets = sparkline_layout(opts["from"], opts["to"])
        rows = self._stats(
            tenant_id,
            logsql_stats.session_trend_query(self._tenant(tenant_id), opts, interval),
            opts,
            limit=max(buckets, 1) + 2,
        )
        return {"points": _trend_points(rows, opts["from"], interval, buckets), "truncated": bool(getattr(rows, "truncated", False))}

    def session_journey(self, tenant_id: str, application: str, session_id: str, opts: dict) -> dict:
        tenant = self._tenant(tenant_id)
        header_rows = self._stats(tenant, logsql_stats.journey_stats_query(tenant, application, session_id), opts, limit=1)
        out = {
            "session": {},
            "views": [],
            "actions": [],
            "errors": [],
            "vitals": [],
            "network": [],
            "console": [],
            "truncated": False,
        }
        if not header_rows or int(float(header_rows[0].get("event_count") or 0)) <= 0:
            return out
        header = dict(header_rows[0])
        header.setdefault("rum.application", application)
        header["rum.session.key"] = session_id
        out["session"] = logsql_stats.map_session_row(header)
        events = self._stats(
            tenant,
            logsql_stats.journey_events_query(tenant, application, session_id),
            opts,
            limit=logsql_stats.JOURNEY_EVENT_LIMIT,
        )
        out["truncated"] = bool(getattr(events, "truncated", False)) or len(events) >= logsql_stats.JOURNEY_EVENT_LIMIT
        for event in (parse_event(row) for row in events):
            ts = _fmt(event.get("time"))
            et = event.get("eventType")
            if et == "view":
                out["views"].append(
                    {
                        "eventId": event.get("eventId"),
                        "viewName": event.get("viewName"),
                        "pageUrl": event.get("pageUrl"),
                        "route": event.get("route"),
                        "timestamp": ts,
                        "loadingTimeMs": event.get("durationMs") or 0,
                    }
                )
            elif et == "action":
                out["actions"].append(
                    {
                        "eventId": event.get("eventId"),
                        "actionId": event.get("actionId"),
                        "parentActionId": event.get("parentAction"),
                        "name": event.get("actionName"),
                        "durationMs": event.get("durationMs") or 0,
                        "timestamp": ts,
                    }
                )
            elif et == "error":
                out["errors"].append(
                    {
                        "eventId": event.get("eventId"),
                        "errorType": event.get("errorType"),
                        "message": event.get("errorMessage"),
                        "fingerprint": event.get("fingerprint"),
                        "errorGroupKey": event.get("groupKey"),
                        "traceId": event.get("traceId") or "",
                        "route": event.get("route") or "",
                        "timestamp": ts,
                    }
                )
            elif et == "vital":
                out["vitals"].append(
                    {
                        "eventId": event.get("eventId"),
                        "name": event.get("vitalName"),
                        "value": event.get("vitalValue") or 0,
                        "timestamp": ts,
                    }
                )
        return out

    def list_views(self, tenant_id: str, opts: dict) -> dict:
        mode = opts.get("mode") or "route"
        apps = list(opts.get("applications") or [])
        if not apps:
            return {"mode": mode, "summary": {"lcpP75": 0.0, "inpP75": 0.0, "clsP75": 0.0}, "releases": [], "rows": [], "truncated": False}
        rows = self._stats(tenant_id, logsql_stats.view_stats_query(self._tenant(tenant_id), opts), opts, limit=500)
        mapped = [logsql_stats.map_view_row(row, mode) for row in rows]
        start = opts.get("from")
        end = opts.get("to")
        if isinstance(start, datetime) and isinstance(end, datetime):
            step, buckets = sparkline_layout(start, end)
            spark_rows = self._stats(
                tenant_id,
                logsql_stats.view_spark_query(self._tenant(tenant_id), opts, step),
                opts,
                limit=10000,
            )
            logsql_stats.fill_view_sparks(mapped, spark_rows, start, step, buckets, mode)
        mapped.sort(key=lambda row: row["impact"], reverse=True)
        releases = sorted({row["release"] for row in mapped if row.get("release")})
        def _avg(name: str) -> float:
            values = [row[name] for row in mapped if row[name]]
            return sum(values) / len(values) if values else 0.0
        return {
            "mode": mode,
            "summary": {"lcpP75": _avg("lcpP75"), "inpP75": _avg("inpP75"), "clsP75": _avg("clsP75")},
            "releases": releases,
            "rows": mapped,
            "truncated": bool(getattr(rows, "truncated", False)),
        }

    def list_error_issues(self, tenant_id: str, opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        if not apps:
            return {"issues": [], "truncated": False}
        rows = self._stats(tenant_id, logsql_stats.error_list_query(self._tenant(tenant_id), opts), opts)
        issues = []
        for row in rows:
            item = logsql_stats.map_error_issue(row)
            if item["fingerprint"]:
                issues.append(item)
        return {"issues": issues, "truncated": bool(getattr(rows, "truncated", False))}

    def error_detail(self, tenant_id: str, fingerprint: str, opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        detail = {
            "fingerprint": "",
            "sampleMessage": "",
            "normalizedMessage": "",
            "errorType": "",
            "occurrences": [],
            "signals": [],
            "truncated": False,
        }
        if not apps:
            return detail
        rows = self._stats(tenant_id, logsql_stats.error_detail_query(self._tenant(tenant_id), fingerprint, opts), opts, limit=1)
        if not rows or int(float(rows[0].get("count") or 0)) <= 0:
            return detail
        row = rows[0]
        detail.update(
            {
                "fingerprint": logsql_stats.sample_text(row, "fingerprint") or fingerprint,
                "sampleMessage": logsql_stats.sample_text(row, "message"),
                "normalizedMessage": logsql_stats.sample_text(row, "message"),
                "errorType": logsql_stats.sample_text(row, "error_type"),
                "count": int(float(row.get("count") or 0)),
                "affectedSessions": int(float(row.get("sessions") or 0)),
                "affectedUsers": int(float(row.get("users") or 0)),
                "firstSeen": row.get("start_time") or None,
                "lastSeen": row.get("end_time") or None,
                "truncated": bool(getattr(rows, "truncated", False)),
            }
        )
        return detail

    def funnel_reach(self, tenant_id: str, steps: list[str], opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        if not apps:
            return {"steps": list(steps), "reached": [0] * len(steps), "truncated": False}
        rows = self._stats(
            tenant_id,
            logsql_stats.funnel_query(self._tenant(tenant_id), opts),
            opts,
            limit=logsql_stats.FUNNEL_GROUP_LIMIT,
        )
        window_sec = int(opts.get("windowSeconds") or 0)
        window = timedelta(seconds=window_sec) if window_sec > 0 else timedelta(hours=1)
        events = []
        for row in rows:
            seen = _parse_stats_time(row.get("first_seen") or "")
            if seen is None:
                continue
            events.append(
                {
                    "sessionId": row.get("rum.session.key") or row.get("rum.session.id") or "",
                    "route": row.get("rum.view.name") or "",
                    "time": seen,
                    "eventType": "view",
                }
            )
        truncated = bool(getattr(rows, "truncated", False)) or len(rows) >= logsql_stats.FUNNEL_GROUP_LIMIT
        return {"steps": list(steps), "reached": funnel_reached(events, steps, window), "truncated": truncated}

    def list_releases(self, tenant_id: str, opts: dict) -> dict:
        apps = list(opts.get("applications") or [])
        if not apps:
            return {"releases": [], "truncated": False}
        tenant = self._tenant(tenant_id)
        rows = self._stats(tenant, logsql_stats.release_stats_query(tenant, opts), opts)
        first_seen = self._stats(tenant, logsql_stats.release_first_issue_query(tenant, opts), opts, limit=5000)
        new_by_release: dict[str, int] = {}
        for row in first_seen:
            release = logsql_stats.sample_text(row, "release")
            if release:
                new_by_release[release] = new_by_release.get(release, 0) + 1
        releases = [logsql_stats.map_release_row(row, new_by_release.get(row.get("rum.release") or "", 0)) for row in rows]
        releases = [row for row in releases if row["release"]]
        return {
            "releases": releases,
            "truncated": bool(getattr(rows, "truncated", False)) or bool(getattr(first_seen, "truncated", False)),
        }

    def monitor_metric(self, tenant_id: str, opts: dict) -> float | None:
        apps = list(opts.get("applications") or [])
        if not apps and not (opts.get("application") or "").strip():
            return None
        metric = (opts.get("metric") or "").strip()
        rows = self._stats(tenant_id, logsql_stats.monitor_metric_query(self._tenant(tenant_id), opts), opts, limit=1)
        if not rows:
            return None
        row = rows[0]
        if metric == "error_rate":
            sessions = float(row.get("sessions") or 0)
            if sessions <= 0:
                return None
            return float(row.get("errored") or 0) / sessions
        value = row.get("value")
        if value is None or value == "":
            return None
        return float(value)

    def metric_series(self, tenant_id: str, opts: dict) -> list[dict]:
        buckets = int(opts.get("points") or 12)
        if buckets <= 0:
            buckets = 12
        start = opts["from"]
        end = opts["to"]
        width = end - start
        if width.total_seconds() <= 0:
            width = timedelta(hours=1)
        step = width / buckets
        points = [{"atMs": int((start + step * i).timestamp() * 1000), "value": 0.0} for i in range(buckets)]
        apps = list(opts.get("applications") or [])
        if not apps and not (opts.get("application") or "").strip():
            return points
        metric = (opts.get("metric") or "").strip()
        rows = self._stats(
            tenant_id,
            logsql_stats.metric_series_query(self._tenant(tenant_id), opts, step),
            opts,
            limit=buckets + 2,
        )
        for row in rows:
            seen = _parse_stats_time(row.get("_time") or "")
            if seen is None:
                continue
            idx = int((seen - start) / step)
            if idx < 0 or idx >= buckets:
                continue
            if metric == "error_rate":
                sessions = float(row.get("sessions") or 0)
                points[idx]["value"] = (float(row.get("errored") or 0) / sessions) if sessions else 0.0
            else:
                points[idx]["value"] = float(row.get("value") or 0)
        return points

    def _stats(self, tenant_id: str, query: str, opts: dict, limit: int = 0):
        if limit <= 0:
            limit = 0
        return self.client.query_logs(query, opts.get("from"), opts.get("to"), limit)


def _fmt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stats_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if str(value).isdigit():
            raw = int(value)
            if raw > 10**15:
                return datetime.fromtimestamp(raw / 1_000_000_000, tz=timezone.utc)
            if raw > 10**12:
                return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None


def _trend_points(rows, start: datetime, interval: timedelta, buckets: int) -> list[dict]:
    n = max(buckets, 1)
    sec = max(60, int(interval.total_seconds()))
    totals = [0] * n
    errored = [0] * n
    start_ts = start.timestamp()
    for row in rows:
        seen = _parse_stats_time(row.get("_time") or "")
        if seen is None:
            continue
        idx = int((seen.timestamp() - start_ts) // sec)
        if idx < 0:
            continue
        if idx >= n:
            idx = n - 1
        totals[idx] = int(float(row.get("total") or 0))
        errored[idx] = int(float(row.get("errored") or 0))
    return [
        {"atMs": int((start_ts + i * sec) * 1000), "total": totals[i], "errored": errored[i]}
        for i in range(n)
    ]
