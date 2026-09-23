from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.rum.services.victoria_client import (
    VictoriaClient,
    aggregate_sessions,
    funnel_reached,
    health_from_events,
    parse_event,
    percentile,
    quote_logsql,
    rum_apps_filter,
    session_trend_points,
    sparkline_layout,
    traffic_ok,
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
        devices = {"mobile": 0, "desktop": 0}
        envs: dict[str, dict] = {}
        releases: dict[str, dict] = {}
        country_sessions: dict[str, set[str]] = {}
        env_sessions: dict[str, set[str]] = {}
        rel_sessions: dict[str, set[str]] = {}
        for event in events:
            if event.get("eventType") == "view":
                country = event.get("country") or ""
                countries.setdefault(country, {"country": country, "views": 0, "sessions": 0})
                countries[country]["views"] += 1
                country_sessions.setdefault(country, set()).add(event.get("sessionId") or "")
            ua = (event.get("userAgent") or "").lower()
            if "mobile" in ua or "android" in ua:
                devices["mobile"] += 1
            elif event.get("userAgent"):
                devices["desktop"] += 1
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
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            limit=8000,
        )
        return aggregate_sessions(events, opts)

    def session_trend(self, tenant_id: str, opts: dict) -> dict:
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            limit=8000,
        )
        return {"points": session_trend_points(events, opts["from"], opts["to"])}

    def session_journey(self, tenant_id: str, application: str, session_id: str, opts: dict) -> dict:
        page = self.list_sessions(
            tenant_id,
            {
                "from": opts["from"],
                "to": opts["to"],
                "applications": [application],
                "sessionId": session_id,
                "limit": 1,
                "traffic": "all",
            },
        )
        out = {
            "session": (page.get("sessions") or [{}])[0] if page.get("sessions") else {},
            "views": [],
            "actions": [],
            "errors": [],
            "vitals": [],
            "network": [],
            "console": [],
        }
        events = self._load_events(
            tenant_id,
            [application],
            opts["from"],
            opts["to"],
            extra=(f'("rum.session.key":{quote_logsql(session_id)}' f' OR "rum.session.id":{quote_logsql(session_id)})'),
            limit=4000,
        )
        for event in events:
            if event.get("sessionId") != session_id:
                continue
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
        start = opts["from"]
        end = opts["to"]
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            start,
            end,
            extra='"rum.event.type":in("view","vital")',
            limit=8000,
        )
        by_key: dict[str, dict] = {}
        release_set: set[str] = set()
        release_filter = (opts.get("release") or "").strip()
        bucket_width, bucket_count = sparkline_layout(start, end)
        all_lcp: list[float] = []
        all_inp: list[float] = []
        all_cls: list[float] = []

        def ensure(key: str, route: str, release: str) -> dict:
            item = by_key.get(key)
            if item is None:
                item = {
                    "key": key if mode == "route" else (release or route or key),
                    "route": route,
                    "release": release,
                    "views": 0,
                    "sessions": 0,
                    "lcpP75": 0.0,
                    "inpP75": 0.0,
                    "clsP75": 0.0,
                    "loadingP75": 0.0,
                    "impact": 0,
                    "dist": {"good": 0, "needsImprove": 0, "poor": 0, "missing": 0},
                    "mom": {"hasDelta": False, "spark": [0.0] * bucket_count},
                    "deviceMix": {"mobile": 0, "desktop": 0},
                    "_sess": set(),
                    "_lcp": [],
                    "_inp": [],
                    "_cls": [],
                    "_loading": [],
                }
                by_key[key] = item
            return item

        for event in events:
            route = event.get("route") or ""
            release = event.get("release") or ""
            key = route
            if mode == "release":
                key = f"{release}\x00{route}"
                if release:
                    release_set.add(release)
                if release_filter and release != release_filter:
                    continue
            item = ensure(key, route, release)
            event_type = event.get("eventType")
            if event_type == "view":
                item["views"] += 1
                if event.get("sessionId"):
                    item["_sess"].add(event["sessionId"])
                ua = event.get("userAgent") or ""
                if _ua_is_mobile(ua):
                    item["deviceMix"]["mobile"] += 1
                else:
                    item["deviceMix"]["desktop"] += 1
                loading = float(event.get("durationMs") or 0)
                if loading > 0:
                    item["_loading"].append(loading)
                event_time = event.get("time")
                if isinstance(event_time, datetime) and bucket_count > 0:
                    offset = event_time - start
                    idx = int(offset.total_seconds() // bucket_width.total_seconds())
                    if idx < 0:
                        continue
                    if idx >= bucket_count:
                        idx = bucket_count - 1
                    item["mom"]["spark"][idx] += 1.0
            elif event_type == "vital":
                name = (event.get("vitalName") or "").lower()
                value = float(event.get("vitalValue") or 0)
                if value <= 0:
                    continue
                if name == "lcp":
                    item["_lcp"].append(value)
                    all_lcp.append(value)
                    bucket = _cwv_bucket("lcp", value)
                    item["dist"][bucket] += 1
                elif name == "inp":
                    item["_inp"].append(value)
                    all_inp.append(value)
                elif name == "cls":
                    item["_cls"].append(value)
                    all_cls.append(value)

        rows = []
        for item in by_key.values():
            item["sessions"] = len(item["_sess"])
            item["lcpP75"] = percentile(item["_lcp"], 0.75)
            item["inpP75"] = percentile(item["_inp"], 0.75)
            item["clsP75"] = percentile(item["_cls"], 0.75)
            item["loadingP75"] = percentile(item["_loading"], 0.75)
            rated = item["dist"]["good"] + item["dist"]["needsImprove"] + item["dist"]["poor"]
            missing = max(0, item["views"] - rated)
            item["dist"]["missing"] = missing
            spark = item["mom"]["spark"]
            item["mom"]["hasDelta"] = any(v > 0 for v in spark)
            # Prefer sessions hit by poor LCP; fall back to view volume for sorting.
            item["impact"] = item["dist"]["poor"] * 10 + item["views"]
            item.pop("_sess", None)
            item.pop("_lcp", None)
            item.pop("_inp", None)
            item.pop("_cls", None)
            item.pop("_loading", None)
            if mode == "release":
                item["key"] = item["release"] or item["route"] or item["key"]
            else:
                item["key"] = item["route"] or item["key"]
            rows.append(item)
        rows.sort(key=lambda row: row["impact"], reverse=True)
        return {
            "mode": mode,
            "summary": {
                "lcpP75": percentile(all_lcp, 0.75),
                "inpP75": percentile(all_inp, 0.75),
                "clsP75": percentile(all_cls, 0.75),
            },
            "releases": sorted(release_set),
            "rows": rows,
        }

    def list_error_issues(self, tenant_id: str, opts: dict) -> dict:
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            extra='"rum.event.type":error',
            limit=4000,
        )
        by_key: dict[str, dict] = {}
        for event in events:
            key = event.get("fingerprint") or event.get("errorMessage") or ""
            item = by_key.get(key)
            if item is None:
                item = {
                    "fingerprint": key,
                    "sampleMessage": event.get("errorMessage") or "",
                    "normalizedMessage": event.get("errorMessage") or "",
                    "errorType": event.get("errorType") or "",
                    "application": event.get("application") or "",
                    "count": 0,
                    "affectedSessions": 0,
                    "firstSeen": None,
                    "lastSeen": None,
                    "_sess": set(),
                }
                by_key[key] = item
            item["count"] += 1
            item["sampleMessage"] = event.get("errorMessage") or item["sampleMessage"]
            item["normalizedMessage"] = item["sampleMessage"]
            item["application"] = event.get("application") or item["application"]
            if event.get("sessionId"):
                item["_sess"].add(event["sessionId"])
            ts = _fmt(event.get("time"))
            if ts and (item["lastSeen"] is None or ts > item["lastSeen"]):
                item["lastSeen"] = ts
            if ts and (item["firstSeen"] is None or ts < item["firstSeen"]):
                item["firstSeen"] = ts
        issues = []
        for item in by_key.values():
            item["affectedSessions"] = len(item["_sess"])
            item.pop("_sess", None)
            issues.append(item)
        issues.sort(key=lambda row: row["count"], reverse=True)
        limit = int(opts.get("limit") or 100)
        if limit > 0:
            issues = issues[:limit]
        return {"issues": issues}

    def error_detail(self, tenant_id: str, fingerprint: str, opts: dict) -> dict:
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            extra='"rum.event.type":error',
            limit=2000,
        )
        detail = {
            "fingerprint": fingerprint,
            "sampleMessage": "",
            "normalizedMessage": "",
            "errorType": "",
            "occurrences": [],
            "signals": [],
        }
        for event in events:
            if event.get("fingerprint") != fingerprint and event.get("groupKey") != fingerprint:
                continue
            detail["occurrences"].append(
                {
                    "eventId": event.get("eventId"),
                    "sessionId": event.get("sessionId"),
                    "userId": event.get("userId"),
                    "timestamp": _fmt(event.get("time")),
                    "traceId": event.get("traceId"),
                }
            )
            if not detail["sampleMessage"]:
                detail["sampleMessage"] = event.get("errorMessage") or ""
                detail["normalizedMessage"] = detail["sampleMessage"]
                detail["errorType"] = event.get("errorType") or ""
                detail["fingerprint"] = event.get("fingerprint") or fingerprint
        return detail

    def funnel_reach(self, tenant_id: str, steps: list[str], opts: dict) -> dict:
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            extra='"rum.event.type":view',
            limit=8000,
        )
        window_sec = int(opts.get("windowSeconds") or 0)
        window = timedelta(seconds=window_sec) if window_sec > 0 else timedelta(hours=1)
        return {"steps": list(steps), "reached": funnel_reached(events, steps, window)}

    def list_releases(self, tenant_id: str, opts: dict) -> dict:
        events = self._load_events(
            tenant_id,
            list(opts.get("applications") or []),
            opts["from"],
            opts["to"],
            limit=8000,
        )
        traffic = opts.get("traffic") or "visitors"
        by_key: dict[str, dict] = {}
        # fingerprint → (first_seen, release_at_first) within the query window
        issue_first: dict[str, tuple[datetime, str]] = {}

        def ensure(release: str) -> dict:
            item = by_key.get(release)
            if item is None:
                item = {
                    "release": release,
                    "errorCount": 0,
                    "distinctIssues": 0,
                    "affectedSessions": 0,
                    "affectedUsers": 0,
                    "firstSeen": None,
                    "lastSeen": None,
                    "lcpP75": 0.0,
                    "inpP75": 0.0,
                    "newIssues": 0,
                    "suspectedRegression": False,
                    "_sess": set(),
                    "_err_sess": set(),
                    "_users": set(),
                    "_issues": set(),
                    "_lcp": [],
                    "_inp": [],
                    "_first": None,
                    "_last": None,
                }
                by_key[release] = item
            return item

        for event in events:
            release = event.get("release") or ""
            if not release or not traffic_ok(event.get("traffic") or "", traffic):
                continue
            item = ensure(release)
            event_time = event.get("time")
            if isinstance(event_time, datetime):
                if item["_first"] is None or event_time < item["_first"]:
                    item["_first"] = event_time
                if item["_last"] is None or event_time > item["_last"]:
                    item["_last"] = event_time
            if event.get("sessionId"):
                item["_sess"].add(event["sessionId"])
            user_id = (event.get("userId") or "").strip()
            if user_id:
                item["_users"].add(user_id)
            event_type = event.get("eventType")
            if event_type == "error":
                if event.get("sessionId"):
                    item["_err_sess"].add(event["sessionId"])
                fingerprint = (event.get("fingerprint") or event.get("errorMessage") or "").strip()
                if fingerprint:
                    item["_issues"].add(fingerprint)
                    if isinstance(event_time, datetime):
                        prev = issue_first.get(fingerprint)
                        if prev is None or event_time < prev[0]:
                            issue_first[fingerprint] = (event_time, release)
            elif event_type == "vital":
                name = (event.get("vitalName") or "").lower()
                value = float(event.get("vitalValue") or 0)
                if value <= 0:
                    continue
                if name == "lcp":
                    item["_lcp"].append(value)
                elif name == "inp":
                    item["_inp"].append(value)

        new_by_release: dict[str, int] = {}
        for _fp, (_ts, release) in issue_first.items():
            new_by_release[release] = new_by_release.get(release, 0) + 1

        rows = []
        for item in by_key.values():
            item["affectedSessions"] = len(item["_sess"])
            item["affectedUsers"] = len(item["_users"])
            item["errorCount"] = len(item["_err_sess"])
            item["distinctIssues"] = len(item["_issues"])
            item["newIssues"] = new_by_release.get(item["release"], 0)
            item["firstSeen"] = _fmt(item["_first"])
            item["lastSeen"] = _fmt(item["_last"])
            item["lcpP75"] = percentile(item["_lcp"], 0.75)
            item["inpP75"] = percentile(item["_inp"], 0.75)
            for key in (
                "_sess",
                "_err_sess",
                "_users",
                "_issues",
                "_lcp",
                "_inp",
                "_first",
                "_last",
            ):
                item.pop(key, None)
            rows.append(item)
        rows.sort(key=lambda row: row["affectedSessions"], reverse=True)
        limit = int(opts.get("limit") or 0)
        if limit > 0:
            rows = rows[:limit]
        return {"releases": rows}

    def monitor_metric(self, tenant_id: str, opts: dict) -> float:
        metric = (opts.get("metric") or "").strip()
        if metric in {"lcp_p75", "inp_p75", "cls_p75", "fcp_p75", "ttfb_p75"}:
            return self._cwv_p75(tenant_id, opts, metric)
        series = self.metric_series(tenant_id, {**opts, "points": 1})
        return float(series[0]["value"]) if series else 0.0

    def _cwv_p75(self, tenant_id: str, opts: dict, metric: str) -> float:
        name = metric[: -len("_p75")] if metric.endswith("_p75") else metric
        events = self._load_events(
            tenant_id,
            [opts.get("application") or ""],
            opts["from"],
            opts["to"],
            extra='"rum.event.type":vital',
            limit=8000,
        )
        values: list[float] = []
        for event in events:
            if (event.get("vitalName") or "").lower() != name:
                continue
            value = float(event.get("vitalValue") or 0)
            if value > 0:
                values.append(value)
        return percentile(values, 0.75)

    def metric_series(self, tenant_id: str, opts: dict) -> list[dict]:
        buckets = int(opts.get("points") or 12)
        if buckets <= 0:
            buckets = 12
        start = opts["from"]
        end = opts["to"]
        metric = (opts.get("metric") or "").strip()
        events = self._load_events(tenant_id, [opts.get("application") or ""], start, end, limit=8000)
        width = end - start
        if width.total_seconds() <= 0:
            width = timedelta(hours=1)
        step = width / buckets
        points = [{"atMs": int((start + step * i).timestamp() * 1000), "value": 0.0} for i in range(buckets)]
        sess = [set() for _ in range(buckets)]
        err_sess = [set() for _ in range(buckets)]
        cwv_vals: list[list[float]] = [[] for _ in range(buckets)]
        cwv_name = metric[: -len("_p75")] if metric.endswith("_p75") else ""
        for event in events:
            event_time = event.get("time")
            if not isinstance(event_time, datetime):
                continue
            idx = int((event_time - start) / step)
            if idx < 0 or idx >= buckets:
                continue
            if event.get("sessionId"):
                sess[idx].add(event["sessionId"])
            if event.get("eventType") == "error" and event.get("sessionId"):
                err_sess[idx].add(event["sessionId"])
            if cwv_name and event.get("eventType") == "vital":
                if (event.get("vitalName") or "").lower() == cwv_name:
                    value = float(event.get("vitalValue") or 0)
                    if value > 0:
                        cwv_vals[idx].append(value)
        for i, point in enumerate(points):
            if metric == "error_rate":
                point["value"] = (len(err_sess[i]) / len(sess[i])) if sess[i] else 0.0
            elif cwv_name:
                point["value"] = percentile(cwv_vals[i], 0.75)
            else:
                point["value"] = float(len(sess[i]))
        return points


def _fmt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
