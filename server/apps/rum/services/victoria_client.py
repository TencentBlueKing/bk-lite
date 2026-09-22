from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


class VictoriaClient:
    """VictoriaLogs / VictoriaTraces LogsQL HTTP client."""

    def __init__(
        self,
        *,
        logs_endpoint: str,
        traces_endpoint: str,
        account_id: int = 0,
        project_id: int = 0,
        timeout_seconds: float = 15.0,
    ):
        self.logs_endpoint = _absolute_url(logs_endpoint, "victoria logs_endpoint")
        self.traces_endpoint = _absolute_url(traces_endpoint, "victoria traces_endpoint")
        self.account_id = str(account_id)
        self.project_id = str(project_id)
        self.timeout_seconds = timeout_seconds or 15.0

    def ping(self) -> None:
        self._ping_host(self.logs_endpoint, "VictoriaLogs")
        self._ping_host(self.traces_endpoint, "VictoriaTraces")

    def query_logs(
        self,
        query: str,
        start: datetime | None,
        end: datetime | None,
        limit: int = 0,
    ) -> list[dict[str, str]]:
        return self._query(self.logs_endpoint, query, start, end, limit)

    def _ping_host(self, base: str, label: str) -> None:
        url = urljoin(base.rstrip("/") + "/", "health")
        req = Request(url, method="GET")
        with urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310 — operator-configured URL
            if resp.status >= 300:
                raise RuntimeError(f"ping {label}: status {resp.status}")

    def _query(
        self,
        base: str,
        query: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[dict[str, str]]:
        url = urljoin(base.rstrip("/") + "/", "select/logsql/query")
        form: dict[str, str] = {"query": query}
        if start is not None:
            form["start"] = str(int(start.timestamp() * 1_000_000_000))
        if end is not None:
            form["end"] = str(int(end.timestamp() * 1_000_000_000))
        if limit > 0:
            form["limit"] = str(limit)
        req = Request(
            url,
            data=urlencode(form).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "AccountID": self.account_id,
                "ProjectID": self.project_id,
            },
        )
        with urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
            body = resp.read(8 << 20)
            if resp.status >= 300:
                raise RuntimeError(f"logsql status {resp.status}: {body[:200]!r}")
        rows: list[dict[str, str]] = []
        for line in body.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            rows.append({str(key): _stringify(value) for key, value in raw.items()})
        return rows


def _absolute_url(raw: str, label: str) -> str:
    value = (raw or "").strip()
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute URL")
    return value.rstrip("/")


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value).rstrip("0").rstrip(".") if "." in repr(value) else str(value)
    if isinstance(value, (int, str)):
        return str(value)
    return json.dumps(value, separators=(",", ":"))


def rum_filter(tenant_id: str, application: str = "") -> str:
    parts = ['"rum.event.type":*']
    if tenant_id:
        parts.append(f'"tenant.id":{json.dumps(tenant_id)}')
    if application:
        parts.append(f'"rum.application":{json.dumps(application)}')
    return " ".join(parts)


def rum_apps_filter(tenant_id: str, apps: list[str]) -> str:
    """Build the per-application LogsQL filter.

    An empty application list is a caller bug (the registry is empty or the
    requested apps were all filtered out); it must never widen the query to the
    whole tenant, so it fails closed instead of returning a tenant-wide filter.
    """
    if not apps:
        raise ValueError("rum_apps_filter requires at least one application")
    quoted = ",".join(json.dumps(app) for app in apps)
    return f'"rum.event.type":* "tenant.id":{json.dumps(tenant_id)} "rum.application":in({quoted})'


def quote_logsql(value: str) -> str:
    return json.dumps(value)


def field(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


def parse_float(raw: str) -> float:
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    if value != value or value in {float("inf"), float("-inf")}:
        return 0.0
    return value


def parse_event(row: dict[str, str]) -> dict:
    event = {
        "time": None,
        "application": field(row, "rum.application", "rumcore.application"),
        "sessionId": field(row, "rum.session.key", "rumcore.session.key") or field(row, "rum.session.id", "rumcore.session.id"),
        "eventType": field(row, "rum.event.type", "rumcore.event.type"),
        "environment": field(row, "rum.environment", "rumcore.environment"),
        "release": field(row, "rum.release", "rumcore.release"),
        "userAgent": field(row, "user_agent.original"),
        "country": field(row, "geo.country.iso_code"),
        "city": field(row, "geo.locality.name"),
        "userId": field(row, "rum.user.id", "rumcore.user.id"),
        "sdkName": field(row, "rum.sdk.name", "rumcore.sdk.name"),
        "sdkVersion": field(row, "rum.sdk.version", "rumcore.sdk.version"),
        "traffic": field(row, "rum.traffic.class", "rumcore.traffic.class"),
        "route": field(row, "rum.context.route", "rum.view.name", "rumcore.context.route", "rumcore.view.name"),
        "pageUrl": field(row, "rum.page.url", "rumcore.page.url"),
        "viewName": field(row, "rum.view.name", "rumcore.view.name"),
        "errorType": field(row, "rum.error.type", "rumcore.error.type"),
        "errorMessage": field(row, "rum.error.message", "rumcore.error.message"),
        "fingerprint": field(row, "rum.error.fingerprint", "rumcore.error.fingerprint"),
        "groupKey": field(row, "rum.error.group_key", "rumcore.error.group_key"),
        "vitalName": "",
        "vitalValue": 0.0,
        "actionName": field(row, "rum.action.name", "rumcore.action.name"),
        "actionId": field(row, "rum.action.id", "rumcore.action.id"),
        "parentAction": field(row, "rum.action.parent.id", "rumcore.action.parent.id"),
        "durationMs": parse_float(
            field(
                row,
                "rum.action.duration_ms",
                "rum.context.loading_time_ms",
                "rumcore.action.duration_ms",
                "rumcore.context.loading_time_ms",
            )
        ),
        "eventId": field(row, "rum.event.id", "rumcore.event.id"),
        "traceId": field(row, "rum.trace.id", "rumcore.trace.id", "trace_id"),
    }
    raw_time = field(row, "_time")
    if raw_time:
        try:
            event["time"] = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            event["time"] = None
    if event["eventType"] == "vital":
        for name in ("lcp", "LCP", "inp", "INP", "cls", "CLS", "fid", "FID", "ttfb", "TTFB", "fcp", "FCP"):
            value = parse_float(
                field(
                    row,
                    f"rum.measurement.{name}",
                    f"rum.vital.{name.lower()}",
                    f"rumcore.measurement.{name}",
                    name,
                    f"rumcore.vital.{name.lower()}",
                )
            )
            if value > 0:
                event["vitalName"] = name.lower()
                event["vitalValue"] = value
                break
    return event


def traffic_ok(class_name: str, want: str) -> bool:
    want = (want or "").strip().lower()
    if want in {"", "all"}:
        return True
    class_name = (class_name or "").lower()
    if want == "visitors":
        return class_name not in {"bot", "synthetic", "crawler"}
    if want == "automated":
        return class_name in {"bot", "synthetic", "crawler"}
    return class_name == want


def sparkline_layout(start: datetime, end: datetime) -> tuple[timedelta, int]:
    span = end - start
    if span <= timedelta(hours=2):
        return timedelta(minutes=5), 12
    if span <= timedelta(hours=36):
        return timedelta(hours=1), 24
    return timedelta(days=1), 7


def session_trend_points(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    """Bucket sessions from `start` through `end`, including the current partial slot.

    Aligning buckets to Unix-epoch multiples drops "now" when `start` is not on a
    slot boundary — a 7d window starting at 09:00 puts today's traffic in slot 7 of
    0..6. Index from `start` and clamp the last partial bucket instead.
    """
    interval, buckets = sparkline_layout(start, end)
    n = max(buckets, 1)
    sec = max(60, int(interval.total_seconds()))
    totals: list[set[str]] = [set() for _ in range(n)]
    errored: list[set[str]] = [set() for _ in range(n)]
    start_ts = start.timestamp()
    for event in events:
        session_id = event.get("sessionId") or ""
        event_time = event.get("time")
        if not session_id or not isinstance(event_time, datetime):
            continue
        idx = int((event_time.timestamp() - start_ts) // sec)
        if idx < 0:
            continue
        if idx >= n:
            idx = n - 1
        totals[idx].add(session_id)
        if event.get("eventType") == "error":
            errored[idx].add(session_id)
    return [
        {
            "atMs": int((start_ts + i * sec) * 1000),
            "total": len(totals[i]),
            "errored": len(errored[i]),
        }
        for i in range(n)
    ]


def clamp_unit(n: float) -> float:
    if n != n or n <= 0:
        return 0.0
    if n >= 1:
        return 1.0
    return n


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((len(ordered) - 1) * p)
    return ordered[idx]


def health_from_events(
    events: list[dict],
    enabled_apps: list[str],
    start: datetime,
    end: datetime,
    buckets: int,
) -> tuple[list[dict], dict[str, list[float]]]:
    by_app = {
        app: {
            "application": app,
            "sessions": 0,
            "views": 0,
            "errors": 0,
            "lcpP75": 0.0,
            "inpP75": 0.0,
            "errorRate": 0.0,
            "environment": "",
            "release": "",
            "sdkVersion": "",
            "lastSeenMs": 0,
        }
        for app in enabled_apps
    }
    sparks = {app: [0.0] * max(buckets, 1) for app in enabled_apps}
    width = end - start
    if width.total_seconds() <= 0:
        width = timedelta(hours=1)
    sessions: dict[str, set[str]] = {}
    errors_by_app: dict[str, set[str]] = {}
    lcp_by_app: dict[str, list[float]] = {}
    inp_by_app: dict[str, list[float]] = {}
    for event in events:
        app = event.get("application") or ""
        row = by_app.get(app)
        if row is None:
            continue
        sessions.setdefault(app, set())
        session_id = event.get("sessionId") or ""
        if session_id:
            sessions[app].add(session_id)
        if event.get("eventType") == "view":
            row["views"] += 1
        if event.get("eventType") == "error":
            row["errors"] += 1
            if session_id:
                errors_by_app.setdefault(app, set()).add(session_id)
        if event.get("eventType") == "vital" and event.get("vitalName") == "lcp":
            lcp_by_app.setdefault(app, []).append(float(event.get("vitalValue") or 0))
        if event.get("eventType") == "vital" and event.get("vitalName") == "inp":
            inp_by_app.setdefault(app, []).append(float(event.get("vitalValue") or 0))
        if event.get("environment"):
            row["environment"] = event["environment"]
        if event.get("release"):
            row["release"] = event["release"]
        if event.get("sdkVersion"):
            row["sdkVersion"] = event["sdkVersion"]
        event_time = event.get("time")
        if isinstance(event_time, datetime):
            ms = int(event_time.timestamp() * 1000)
            if ms > row["lastSeenMs"]:
                row["lastSeenMs"] = ms
            if buckets > 0:
                idx = int((event_time - start) * buckets / width)
                if idx >= buckets:
                    idx = buckets - 1
                if 0 <= idx < buckets and event.get("eventType") == "view":
                    sparks[app][idx] += 1
    out = []
    for app in enabled_apps:
        row = by_app[app]
        row["sessions"] = len(sessions.get(app, set()))
        if row["sessions"] > 0:
            row["errorRate"] = clamp_unit(len(errors_by_app.get(app, set())) / row["sessions"])
        row["lcpP75"] = percentile(lcp_by_app.get(app, []), 0.75)
        row["inpP75"] = percentile(inp_by_app.get(app, []), 0.75)
        out.append(row)
    return out, sparks


def funnel_reached(events: list[dict], steps: list[str], window: timedelta) -> list[int]:
    reached = [0] * len(steps)
    by_session: dict[str, list[tuple[datetime, str]]] = {}
    for event in events:
        session_id = event.get("sessionId") or ""
        if not session_id:
            continue
        event_time = event.get("time") or datetime.min.replace(tzinfo=timezone.utc)
        by_session.setdefault(session_id, []).append((event_time, event.get("route") or ""))
    for hits in by_session.values():
        hits.sort(key=lambda item: item[0])
        step = 0
        start: datetime | None = None
        for event_time, route in hits:
            if step >= len(steps) or route != steps[step]:
                continue
            if step == 0:
                start = event_time
            elif start is not None and event_time - start > window:
                break
            reached[step] += 1
            step += 1
    return reached


def _accepted_session_id(event: dict, opts: dict) -> str:
    sid = event.get("sessionId") or ""
    if not sid:
        return ""
    traffic = opts.get("traffic") or "visitors"
    if not traffic_ok(event.get("traffic") or "", traffic):
        return ""
    session_id = (opts.get("sessionId") or "").strip()
    if session_id and sid != session_id:
        return ""
    session_pref = (opts.get("sessionIdPref") or "").strip()
    if session_pref and not sid.startswith(session_pref):
        return ""
    user_id = (opts.get("userId") or "").strip()
    if user_id and (event.get("userId") or "") != user_id:
        return ""
    country = (opts.get("country") or "").strip()
    if country and (event.get("country") or "") != country:
        return ""
    route = (opts.get("route") or "").strip()
    if route and (event.get("route") or "") != route:
        return ""
    return sid


def _new_session_item(event: dict, sid: str) -> dict:
    return {
        "application": event.get("application") or "",
        "sessionId": sid,
        "startTime": event.get("time"),
        "endTime": event.get("time"),
        "entryRoute": event.get("route") or "",
        "viewCount": 0,
        "errorCount": 0,
        "actionCount": 0,
        "vitalCount": 0,
        "eventIds": set(),
        "userAgent": "",
        "geoCountry": "",
        "geoCity": "",
        "userId": "",
        "environment": "",
        "release": "",
        "sdkName": "",
        "sdkVersion": "",
        "trafficClass": "",
    }


def _accrue_session_event(item: dict, event: dict) -> None:
    if event.get("eventId"):
        item["eventIds"].add(event["eventId"])
    event_time = event.get("time")
    if isinstance(event_time, datetime):
        if item["startTime"] is None or event_time < item["startTime"]:
            item["startTime"] = event_time
            item["entryRoute"] = event.get("route") or item["entryRoute"]
        if item["endTime"] is None or event_time > item["endTime"]:
            item["endTime"] = event_time
    et = event.get("eventType")
    if et == "view":
        item["viewCount"] += 1
    elif et == "error":
        item["errorCount"] += 1
    elif et == "action":
        item["actionCount"] += 1
    elif et == "vital":
        item["vitalCount"] += 1
    if event.get("userAgent"):
        item["userAgent"] = event["userAgent"]
    item["geoCountry"] = event.get("country") or item["geoCountry"]
    item["geoCity"] = event.get("city") or item["geoCity"]
    item["userId"] = event.get("userId") or item["userId"]
    item["environment"] = event.get("environment") or item["environment"]
    item["release"] = event.get("release") or item["release"]
    item["sdkName"] = event.get("sdkName") or item["sdkName"]
    item["sdkVersion"] = event.get("sdkVersion") or item["sdkVersion"]
    item["trafficClass"] = event.get("traffic") or item["trafficClass"]


def _session_row(item: dict) -> dict:
    return {
        "application": item["application"],
        "sessionId": item["sessionId"],
        "startTime": _fmt_dt(item["startTime"]),
        "endTime": _fmt_dt(item["endTime"]),
        "entryRoute": item["entryRoute"],
        "viewCount": item["viewCount"],
        "errorCount": item["errorCount"],
        "actionCount": item["actionCount"],
        "vitalCount": item["vitalCount"],
        "eventCount": len(item["eventIds"]),
        "userAgent": item["userAgent"],
        "geoCountry": item["geoCountry"],
        "geoCity": item["geoCity"],
        "userId": item["userId"],
        "environment": item["environment"],
        "release": item["release"],
        "sdkName": item["sdkName"],
        "sdkVersion": item["sdkVersion"],
        "trafficClass": item["trafficClass"],
    }


def _sessions_summary(sessions: list[dict]) -> dict:
    summary = {"total": len(sessions), "errored": 0, "replayed": 0, "medianDurationMs": 0}
    durations: list[float] = []
    for row in sessions:
        if row["errorCount"] > 0:
            summary["errored"] += 1
        start = _parse_dt(row["startTime"])
        end = _parse_dt(row["endTime"])
        if start and end:
            durations.append((end - start).total_seconds() * 1000)
    if durations:
        durations.sort()
        summary["medianDurationMs"] = int(durations[len(durations) // 2])
    return summary


def aggregate_sessions(events: list[dict], opts: dict) -> dict:
    has_error = bool(opts.get("hasError"))
    by_key: dict[str, dict] = {}
    for event in events:
        sid = _accepted_session_id(event, opts)
        if not sid:
            continue
        key = f"{event.get('application')}\x00{sid}"
        item = by_key.get(key)
        if item is None:
            item = _new_session_item(event, sid)
            by_key[key] = item
        _accrue_session_event(item, event)

    sessions = [_session_row(item) for item in by_key.values() if not has_error or item["errorCount"] > 0]
    sessions.sort(key=lambda row: row.get("startTime") or "", reverse=True)
    summary = _sessions_summary(sessions)
    limit = int(opts.get("limit") or 200)
    if limit <= 0:
        limit = 200
    offset = max(0, int(opts.get("offset") or 0))
    return {"sessions": sessions[offset : offset + limit], "summary": summary}


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
