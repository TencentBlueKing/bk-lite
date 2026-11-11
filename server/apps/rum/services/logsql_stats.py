"""LogsQL stats queries for RUM analytics. VictoriaLogs contract: victoria-logs:v1.38.0."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from apps.rum.services.victoria_client import clamp_unit, parse_float, quote_logsql, rum_apps_filter

FUNNEL_GROUP_LIMIT = 50000
JOURNEY_EVENT_LIMIT = 20000
REPLAY_CHUNK = 200
# One row per session. Same ceiling as funnel groups; hitting it sets truncated.
SESSION_GROUP_LIMIT = 50000

SESSION_SORTS = {
    "start": "sort by (start_time desc)",
    "errors": "sort by (error_count desc, start_time desc)",
    "duration": "sort by (duration desc, start_time desc)",
    "impact": "sort by (error_count desc, duration desc, start_time desc)",
}

ERROR_SORTS = {
    "count": "sort by (count desc)",
    "sessions": "sort by (sessions desc, count desc)",
    "users": "sort by (users desc, count desc)",
    "relevance": "sort by (count desc, duration desc, start_time desc)",
}

# victoria-logs:v1.38.0 has no stats any(). values() returns a JSON array;
# sample_text keeps one element. The picked element is not time-ordered.
_SESSION_STATS = (
    "stats by (`rum.application`, `rum.session.key`, `rum.session.id`) "
    "count() as event_count, "
    "count_uniq(`rum.event.id`) as events, "
    "min(_time) as start_time, "
    "max(_time) as end_time, "
    'count() if ("rum.event.type":view) as view_count, '
    'count() if ("rum.event.type":error) as error_count, '
    'count() if ("rum.event.type":action) as action_count, '
    'count() if ("rum.event.type":vital) as vital_count, '
    "values(`user_agent.original`) as user_agent, "
    "values(`geo.country.iso_code`) as country, "
    "values(`geo.locality.name`) as city, "
    "values(`rum.user.id`) as user_id, "
    "values(`rum.environment`) as environment, "
    "values(`rum.release`) as release, "
    "values(`rum.sdk.name`) as sdk_name, "
    "values(`rum.sdk.version`) as sdk_version, "
    "values(`rum.traffic.class`) as traffic_class, "
    "values(`rum.view.name`) as entry_route"
)


def session_page_query(tenant_id: str, opts: dict) -> str:
    grouped = _session_grouped(tenant_id, opts)
    order = SESSION_SORTS.get((opts.get("orderBy") or "impact").strip(), SESSION_SORTS["impact"])
    limit = _positive(opts.get("limit"), 200)
    offset = max(0, int(opts.get("offset") or 0))
    return f"{grouped} | {order} | offset {offset} | limit {limit}"


def session_summary_query(tenant_id: str, opts: dict) -> str:
    grouped = _session_grouped(tenant_id, opts)
    return f"{grouped} | stats count() as total, " "count() if (error_count:>0) as errored, " "quantile(0.5, duration) as median"


def session_record_epoch_query(tenant_id: str) -> str:
    tenant = quote_logsql((tenant_id or "").strip() or "core")
    return f'"rum.event.type":session_end "tenant.id":{tenant} | stats min(_time) as first_seen'


def session_record_page_query(tenant_id: str, opts: dict, fetch_limit: int) -> str:
    """Top ``fetch_limit`` ended sessions. The caller merges these with in-progress rows."""

    order = SESSION_SORTS.get((opts.get("orderBy") or "impact").strip(), SESSION_SORTS["impact"])
    return f"{_record_grouped(tenant_id, opts)} | {order} | limit {max(1, int(fetch_limit))}"


def session_record_summary_query(tenant_id: str, opts: dict) -> str:
    """Counts and median over every matching ended session, not just the page."""

    return (
        f"{_record_grouped(tenant_id, opts)} | stats count() as total, "
        "count() if (error_count:>0) as errored, "
        "quantile(0.5, duration) as median"
    )


def session_record_trend_query(tenant_id: str, opts: dict, origin_ms: int, step_ms: int) -> str:
    """One count per session, in the bucket that contains its start."""

    grouped = _record_grouped(tenant_id, opts)
    origin = int(origin_ms)
    step = max(1, int(step_ms))
    return (
        f"{grouped} | filter start_time:>={origin} "
        f"| math floor((start_time - {origin}) / {step}) as bucket "
        "| stats by (bucket) count() as total, count() if (error_count:>0) as errored"
    )


def session_record_app_count_query(tenant_id: str, opts: dict) -> str:
    grouped = _record_grouped(tenant_id, opts)
    return f"{grouped} | stats by (`rum.application`) " "count() as sessions, count() if (error_count:>0) as errored"


def session_record_present_query(tenant_id: str, apps: list[str], keys: list[str]) -> str:
    """Which of these session keys already have a record. No list filters."""

    quoted = ",".join(quote_logsql(key) for key in keys)
    extra = f'"rum.event.type":session_end "rum.session.key":in({quoted})'
    base = _filtered(tenant_id, {"applications": apps, "traffic": "all"}, extra)
    return f"{base} | stats by (`rum.application`, `rum.session.key`) count() as copies"


def session_live_group_query(tenant_id: str, opts: dict, active_after: datetime | None = None) -> str:
    grouped = _session_grouped(tenant_id, opts)
    if active_after is not None:
        if active_after.tzinfo is None:
            active_after = active_after.replace(tzinfo=timezone.utc)
        stamp = _fmt_dt(active_after.astimezone(timezone.utc))
        grouped += f" | filter end_time:>={stamp}"
    return f"{grouped} | limit {SESSION_GROUP_LIMIT}"


def session_trend_query(tenant_id: str, opts: dict, step: timedelta) -> str:
    base = _filtered(tenant_id, opts, '("rum.session.key":* OR "rum.session.id":*) NOT "rum.event.type":session_end')
    bucket = _time_bucket(step)
    return (
        f"{base} | stats by ({bucket}) "
        "count_uniq(`rum.session.key`) as total, "
        'count_uniq(`rum.session.key`) if ("rum.event.type":error) as errored'
    )


def view_stats_query(tenant_id: str, opts: dict) -> str:
    extra = ['"rum.event.type":in("view","vital")']
    release = (opts.get("release") or "").strip()
    if release:
        extra.append(f'"rum.release":{quote_logsql(release)}')
    base = _filtered(tenant_id, opts, " ".join(extra))
    group = "`rum.view.name`"
    if (opts.get("mode") or "route") == "release":
        group = "`rum.release`, `rum.view.name`"
    return (
        f"{base} | stats by ({group}) "
        'count() if ("rum.event.type":view) as views, '
        "count_uniq(`rum.session.key`) as sessions, "
        "quantile(0.75, `rum.vital.lcp`) if (`rum.vital.lcp`:*) as lcp_p75, "
        "quantile(0.75, `rum.vital.inp`) if (`rum.vital.inp`:*) as inp_p75, "
        "quantile(0.75, `rum.vital.cls`) if (`rum.vital.cls`:*) as cls_p75, "
        "quantile(0.75, `rum.context.loading_time_ms`) if (`rum.context.loading_time_ms`:*) as loading_p75, "
        "count() if (`rum.vital.lcp`:<=2500) as lcp_good, "
        "count() if (`rum.vital.lcp`:>2500 AND `rum.vital.lcp`:<=4000) as lcp_needs, "
        "count() if (`rum.vital.lcp`:>4000) as lcp_poor, "
        "count() if ("
        '"rum.event.type":view ("user_agent.original":Mobile OR '
        '"user_agent.original":Android OR "user_agent.original":iPhone)'
        ") as mobile, "
        'count() if ("rum.event.type":view) as view_events '
        "| sort by (views desc) | offset 0 | limit 500"
    )


def view_spark_query(tenant_id: str, opts: dict, step: timedelta) -> str:
    extra = ['"rum.event.type":view']
    release = (opts.get("release") or "").strip()
    if release:
        extra.append(f'"rum.release":{quote_logsql(release)}')
    base = _filtered(tenant_id, opts, " ".join(extra))
    group = "`rum.view.name`"
    if (opts.get("mode") or "route") == "release":
        group = "`rum.release`, `rum.view.name`"
    bucket = _time_bucket(step)
    return f"{base} | stats by ({group}, {bucket}) count() as views | sort by ({bucket}) | limit 10000"


def fill_view_sparks(rows: list[dict], spark_rows: list[dict], start: datetime, step: timedelta, buckets: int, mode: str) -> None:
    n = max(buckets, 1)
    sec = max(60, int(step.total_seconds()))
    start_ts = start.timestamp()
    series: dict[str, list[int]] = {}
    for raw in spark_rows:
        seen = _parse_time(_text(raw, "_time"))
        if seen is None:
            continue
        idx = int((seen.timestamp() - start_ts) // sec)
        if idx < 0:
            continue
        if idx >= n:
            idx = n - 1
        key = _spark_key(_text(raw, "rum.view.name"), _text(raw, "rum.release"), mode)
        bucket = series.setdefault(key, [0] * n)
        bucket[idx] += int(_num(raw, "views"))
    for row in rows:
        key = _spark_key(str(row.get("route") or ""), str(row.get("release") or ""), mode)
        spark = series.get(key) or [0] * n
        row["mom"] = {"hasDelta": any(point > 0 for point in spark), "spark": spark}


def _spark_key(route: str, release: str, mode: str) -> str:
    if mode == "release":
        return f"{release}\x00{route}"
    return route


def error_list_query(tenant_id: str, opts: dict) -> str:
    extra = ['"rum.event.type":error']
    release = (opts.get("release") or "").strip()
    if release:
        extra.append(f'"rum.release":{quote_logsql(release)}')
    user_id = (opts.get("userId") or "").strip()
    if user_id:
        extra.append(f'"rum.user.id":{quote_logsql(user_id)}')
    base = _filtered(tenant_id, opts, " ".join(extra))
    order = ERROR_SORTS.get((opts.get("orderBy") or "count").strip(), ERROR_SORTS["count"])
    limit = _positive(opts.get("limit"), 100)
    offset = max(0, int(opts.get("offset") or 0))
    return (
        f"{base} | stats by (`rum.error.fingerprint`, `rum.error.group_key`) "
        "count() as count, "
        "count_uniq(`rum.session.key`) as sessions, "
        "count_uniq(`rum.user.id`) as users, "
        "min(_time) as start_time, "
        "max(_time) as end_time, "
        "values(`rum.error.message`) as message, "
        "values(`rum.error.type`) as error_type, "
        "values(`rum.application`) as application "
        "| math (end_time - start_time) as duration "
        f"| {order} | offset {offset} | limit {limit}"
    )


def error_detail_query(tenant_id: str, fingerprint: str, opts: dict) -> str:
    base = _filtered(
        tenant_id,
        opts,
        f'"rum.event.type":error ("rum.error.fingerprint":{quote_logsql(fingerprint)}' f' OR "rum.error.group_key":{quote_logsql(fingerprint)})',
    )
    return (
        f"{base} | stats count() as count, "
        "count_uniq(`rum.session.key`) as sessions, "
        "count_uniq(`rum.user.id`) as users, "
        "min(_time) as start_time, "
        "max(_time) as end_time, "
        "values(`rum.error.message`) as message, "
        "values(`rum.error.type`) as error_type, "
        "values(`rum.error.fingerprint`) as fingerprint"
    )


def release_stats_query(tenant_id: str, opts: dict) -> str:
    base = _filtered(tenant_id, opts, '"rum.release":*')
    limit = _positive(opts.get("limit"), 100)
    return (
        f"{base} | stats by (`rum.release`) "
        "count_uniq(`rum.session.key`) as affected_sessions, "
        "count_uniq(`rum.user.id`) as affected_users, "
        'count_uniq(`rum.session.key`) if ("rum.event.type":error) as error_sessions, '
        'count_uniq(`rum.error.fingerprint`) if ("rum.event.type":error) as distinct_issues, '
        "min(_time) as first_seen, "
        "max(_time) as last_seen, "
        "quantile(0.75, `rum.vital.lcp`) if (`rum.vital.lcp`:*) as lcp_p75, "
        "quantile(0.75, `rum.vital.inp`) if (`rum.vital.inp`:*) as inp_p75 "
        f"| sort by (affected_sessions desc) | offset 0 | limit {limit}"
    )


def release_first_issue_query(tenant_id: str, opts: dict) -> str:
    base = _filtered(tenant_id, opts, '"rum.event.type":error "rum.error.fingerprint":*')
    return (
        f"{base} | stats by (`rum.error.fingerprint`) "
        "min(_time) as first_seen, values(`rum.release`) as release "
        "| sort by (first_seen) | offset 0 | limit 5000"
    )


def funnel_query(tenant_id: str, opts: dict) -> str:
    base = _filtered(tenant_id, opts, '"rum.event.type":view ("rum.session.key":* OR "rum.session.id":*)')
    return (
        f"{base} | stats by (`rum.session.key`, `rum.view.name`) min(_time) as first_seen "
        f"| sort by (first_seen) | offset 0 | limit {FUNNEL_GROUP_LIMIT}"
    )


def journey_stats_query(tenant_id: str, application: str, session_id: str) -> str:
    base = rum_apps_filter(tenant_id, [application]) + " " + _session_eq(session_id)
    return (
        f"{base} | stats count() as event_count, "
        "min(_time) as start_time, "
        "max(_time) as end_time, "
        'count() if ("rum.event.type":view) as view_count, '
        'count() if ("rum.event.type":error) as error_count, '
        'count() if ("rum.event.type":action) as action_count, '
        "count_uniq(`rum.event.id`) as events, "
        "values(`rum.view.name`) as entry_route, "
        "values(`user_agent.original`) as user_agent, "
        "values(`rum.user.id`) as user_id, "
        "values(`rum.release`) as release, "
        "values(`rum.environment`) as environment, "
        "values(`rum.traffic.class`) as traffic_class"
    )


def journey_events_query(tenant_id: str, application: str, session_id: str) -> str:
    base = rum_apps_filter(tenant_id, [application]) + " " + _session_eq(session_id)
    return f"{base} | sort by (_time) | offset 0 | limit {JOURNEY_EVENT_LIMIT}"


def monitor_metric_query(tenant_id: str, opts: dict) -> str:
    metric = (opts.get("metric") or "").strip()
    base = _filtered(tenant_id, {**opts, "applications": _metric_apps(opts)}, "")
    if metric in {"lcp_p75", "inp_p75", "cls_p75", "fcp_p75", "ttfb_p75"}:
        name = metric[: -len("_p75")]
        return f'{base} "rum.event.type":vital | stats quantile(0.75, `rum.vital.{name}`) as value'
    if metric == "error_rate":
        return f"{base} | stats count_uniq(`rum.session.key`) as sessions, " 'count_uniq(`rum.session.key`) if ("rum.event.type":error) as errored'
    return f"{base} | stats count_uniq(`rum.session.key`) as value"


def metric_series_query(tenant_id: str, opts: dict, step: timedelta) -> str:
    metric = (opts.get("metric") or "").strip()
    base = _filtered(tenant_id, {**opts, "applications": _metric_apps(opts)}, "")
    bucket = _time_bucket(step)
    if metric == "error_rate":
        return (
            f"{base} | stats by ({bucket}) "
            "count_uniq(`rum.session.key`) as sessions, "
            'count_uniq(`rum.session.key`) if ("rum.event.type":error) as errored'
        )
    if metric.endswith("_p75"):
        name = metric[: -len("_p75")]
        return f'{base} "rum.event.type":vital | stats by ({bucket}) ' f"quantile(0.75, `rum.vital.{name}`) as value"
    return f"{base} | stats by ({bucket}) count_uniq(`rum.session.key`) as value"


def map_session_row(row: dict) -> dict:
    start = _parse_time(_text(row, "start_time"))
    end = _parse_time(_text(row, "end_time"))
    session_id = _text(row, "rum.session.key") or _text(row, "rum.session.id")
    return {
        "application": _text(row, "rum.application"),
        "sessionId": session_id,
        "startTime": _fmt_dt(start),
        "endTime": _fmt_dt(end),
        "entryRoute": sample_text(row, "entry_route"),
        "viewCount": int(_num(row, "view_count")),
        "errorCount": int(_num(row, "error_count")),
        "actionCount": int(_num(row, "action_count")),
        "vitalCount": int(_num(row, "vital_count")),
        "eventCount": int(_num(row, "events") or _num(row, "event_count")),
        "userAgent": sample_text(row, "user_agent"),
        "geoCountry": sample_text(row, "country"),
        "geoCity": sample_text(row, "city"),
        "userId": sample_text(row, "user_id"),
        "environment": sample_text(row, "environment"),
        "release": sample_text(row, "release"),
        "sdkName": sample_text(row, "sdk_name"),
        "sdkVersion": sample_text(row, "sdk_version"),
        "trafficClass": sample_text(row, "traffic_class"),
    }


def map_session_summary(row: dict | None) -> dict:
    if not row:
        return {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0}
    # LogsQL `end_time - start_time` is nanoseconds. A 4-minute session is
    # ~2.4e11, below the old 1e12 cutoff, so the KPI was shown as hours.
    median_ns = _num(row, "median")
    return {
        "total": int(_num(row, "total")),
        "errored": int(_num(row, "errored")),
        "replayed": 0,
        "medianDurationMs": int(median_ns / 1_000_000),
    }


def map_record_summary(row: dict | None) -> dict:
    """Summary over session records. ``duration`` is already milliseconds."""

    if not row:
        return {"total": 0, "errored": 0, "replayed": 0, "medianDurationMs": 0}
    return {
        "total": int(_num(row, "total")),
        "errored": int(_num(row, "errored")),
        "replayed": 0,
        "medianDurationMs": int(_num(row, "median")),
    }


def map_view_row(row: dict, mode: str) -> dict:
    route = _text(row, "rum.view.name")
    release = _text(row, "rum.release")
    views = int(_num(row, "views"))
    good = int(_num(row, "lcp_good"))
    needs = int(_num(row, "lcp_needs"))
    poor = int(_num(row, "lcp_poor"))
    rated = good + needs + poor
    mobile = int(_num(row, "mobile"))
    key = f"{release}\x00{route}" if mode == "release" else route
    return {
        "key": (release or route or key) if mode == "release" else (route or key),
        "route": route,
        "release": release,
        "views": views,
        "sessions": int(_num(row, "sessions")),
        "lcpP75": _num(row, "lcp_p75"),
        "inpP75": _num(row, "inp_p75"),
        "clsP75": _num(row, "cls_p75"),
        "loadingP75": _num(row, "loading_p75"),
        "impact": poor * 10 + views,
        "dist": {
            "good": good,
            "needsImprove": needs,
            "poor": poor,
            "missing": max(0, views - rated),
        },
        "mom": {"hasDelta": False, "spark": []},
        "deviceMix": {"mobile": mobile, "desktop": max(0, views - mobile)},
    }


def map_error_issue(row: dict) -> dict:
    start = _fmt_dt(_parse_time(_text(row, "start_time")))
    end = _fmt_dt(_parse_time(_text(row, "end_time")))
    return {
        "fingerprint": _text(row, "rum.error.fingerprint") or _text(row, "rum.error.group_key"),
        "sampleMessage": sample_text(row, "message"),
        "normalizedMessage": sample_text(row, "message"),
        "errorType": sample_text(row, "error_type"),
        "application": sample_text(row, "application"),
        "count": int(_num(row, "count")),
        "affectedSessions": int(_num(row, "sessions")),
        "affectedUsers": int(_num(row, "users")),
        "firstSeen": start,
        "lastSeen": end,
    }


def map_release_row(row: dict, new_issues: int) -> dict:
    return {
        "release": _text(row, "rum.release"),
        "errorCount": int(_num(row, "error_sessions")),
        "distinctIssues": int(_num(row, "distinct_issues")),
        "affectedSessions": int(_num(row, "affected_sessions")),
        "affectedUsers": int(_num(row, "affected_users")),
        "firstSeen": _fmt_dt(_parse_time(_text(row, "first_seen"))),
        "lastSeen": _fmt_dt(_parse_time(_text(row, "last_seen"))),
        "lcpP75": _num(row, "lcp_p75"),
        "inpP75": _num(row, "inp_p75"),
        "newIssues": new_issues,
        "suspectedRegression": False,
    }


# Count fields only. Copies of one session_end row take max; do not use the log row count.
# duration_ms is already milliseconds, unlike the raw-event (end - start) nanoseconds.
_SESSION_RECORD_STATS = (
    "stats by (`rum.application`, `rum.session.key`) "
    "max(`rum.session.event_count`) as event_count, "
    "max(`rum.session.view_count`) as view_count, "
    "max(`rum.session.error_count`) as error_count, "
    "max(`rum.session.duration_ms`) as duration, "
    "max(`rum.session.started_at_ms`) as start_time, "
    "max(_time) as end_time, "
    "values(`rum.view.name`) as entry_route, "
    "values(`rum.user.id`) as user_id, "
    "values(`rum.environment`) as environment, "
    "values(`rum.release`) as release, "
    "values(`rum.traffic.class`) as traffic_class"
)


def _record_grouped(tenant_id: str, opts: dict) -> str:
    """Ended sessions with list filters pushed onto record fields.

    Country is not a record field. Callers skip this query when a country is set.
    Route matches the entry view only; user matches the first user stored on the record.
    """

    extras = ['"rum.event.type":session_end']
    session_id = (opts.get("sessionId") or "").strip()
    if session_id:
        extras.append(_session_eq(session_id))
    prefix = (opts.get("sessionIdPrefix") or "").strip()
    if prefix:
        extras.append(_prefix_filter(prefix))
    user_id = (opts.get("userId") or "").strip()
    if user_id:
        extras.append(f'"rum.user.id":{quote_logsql(user_id)}')
    route = (opts.get("route") or "").strip()
    if route:
        extras.append(f'"rum.view.name":{quote_logsql(route)}')
    if opts.get("hasError"):
        extras.append("`rum.session.error_count`:>0")
    end = opts.get("to")
    if isinstance(end, datetime):
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        extras.append(f"`rum.session.started_at_ms`:<={int(end.timestamp() * 1000)}")
    base = _filtered(tenant_id, opts, " ".join(extras))
    return f"{base} | {_SESSION_RECORD_STATS}"


def _session_scope_extras(opts: dict) -> list[str]:
    extras: list[str] = []
    session_id = (opts.get("sessionId") or "").strip()
    if session_id:
        extras.append(_session_eq(session_id))
    prefix = (opts.get("sessionIdPrefix") or "").strip()
    if prefix:
        extras.append(_prefix_filter(prefix))
    user_id = (opts.get("userId") or "").strip()
    if user_id:
        extras.append(f'"rum.user.id":{quote_logsql(user_id)}')
    country = (opts.get("country") or "").strip()
    if country:
        extras.append(f'"geo.country.iso_code":{quote_logsql(country)}')
    route = (opts.get("route") or "").strip()
    if route:
        quoted = quote_logsql(route)
        extras.append(f'("rum.view.name":{quoted} OR "rum.context.route":{quoted})')
    return extras


def _session_grouped(tenant_id: str, opts: dict) -> str:
    # session_end rows live in the same stream. Counting them would add a fake event.
    extras = ['("rum.session.key":* OR "rum.session.id":*)', 'NOT "rum.event.type":session_end']
    extras.extend(_session_scope_extras(opts))
    base = _filtered(tenant_id, opts, " ".join(extras))
    grouped = f"{base} | {_SESSION_STATS} | math (end_time - start_time) as duration"
    if opts.get("hasError"):
        grouped += " | filter error_count:>0"
    return grouped


def _filtered(tenant_id: str, opts: dict, extra: str) -> str:
    apps = list(opts.get("applications") or [])
    query = rum_apps_filter(tenant_id, apps)
    traffic = _traffic_filter(opts.get("traffic") or "visitors")
    parts = [query]
    if traffic:
        parts.append(traffic)
    if extra:
        parts.append(extra)
    return " ".join(part for part in parts if part)


def _traffic_filter(traffic: str) -> str:
    want = (traffic or "").strip().lower()
    if want in {"", "all"}:
        return ""
    if want == "visitors":
        return 'NOT "rum.traffic.class":in("bot","synthetic","crawler")'
    if want == "automated":
        return '"rum.traffic.class":in("bot","synthetic","crawler")'
    return f'"rum.traffic.class":{quote_logsql(want)}'


def _session_eq(session_id: str) -> str:
    quoted = quote_logsql(session_id)
    return f'("rum.session.key":{quoted} OR "rum.session.id":{quoted})'


def _prefix_filter(prefix: str) -> str:
    token = json.dumps(prefix) + "*"
    return f'("rum.session.key":{token} OR "rum.session.id":{token})'


def _metric_apps(opts: dict) -> list[str]:
    apps = list(opts.get("applications") or [])
    if apps:
        return apps
    application = (opts.get("application") or "").strip()
    return [application] if application else []


def _time_bucket(step: timedelta) -> str:
    seconds = max(60, int(step.total_seconds()))
    if seconds % 86400 == 0:
        return f"_time:{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"_time:{seconds // 3600}h"
    return f"_time:{max(1, seconds // 60)}m"


def _positive(value, default: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _text(row: dict, key: str) -> str:
    return str(row.get(key) or "").strip()


def sample_text(row: dict, key: str) -> str:
    """Read one sample from a values() cell.

    v1.38.0 encodes values() as a JSON array string. A plain string is returned
    unchanged so callers that already collapsed the sample keep working.
    """
    value = row.get(key)
    if isinstance(value, list):
        items = value
    else:
        text = str(value or "").strip()
        if not text.startswith("["):
            return text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(parsed, list):
            return text
        items = parsed
    for item in items:
        sample = str(item or "").strip()
        if sample:
            return sample
    return ""


def _num(row: dict, key: str) -> float:
    return parse_float(str(row.get(key) or ""))


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        if value.isdigit():
            raw = int(value)
            if raw > 10**15:
                return datetime.fromtimestamp(raw / 1_000_000_000, tz=timezone.utc)
            if raw > 10**12:
                return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None


def _fmt_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


_OVERVIEW_FACETS = {"rum.environment", "rum.release"}
# Same User-Agent words as view_stats_query. A session with any of them is mobile.
_MOBILE_UA = '"user_agent.original":Mobile OR "user_agent.original":Android OR "user_agent.original":iPhone'


def catalog_health_query(tenant_id: str, apps: list[str]) -> str:
    base = rum_apps_filter(tenant_id, apps)
    return (
        f"{base} | stats by (`rum.application`) "
        "count_uniq(`rum.session.key`) as sessions, "
        'count() if ("rum.event.type":view) as views, '
        'count() if ("rum.event.type":error) as errors, '
        'count_uniq(`rum.session.key`) if ("rum.event.type":error) as errored_sessions, '
        "quantile(0.75, `rum.measurement.lcp`) if (`rum.measurement.lcp`:*) as lcp_measurement_p75, "
        "quantile(0.75, `rum.vital.lcp`) if (`rum.vital.lcp`:*) as lcp_p75, "
        "quantile(0.75, `rum.measurement.inp`) if (`rum.measurement.inp`:*) as inp_measurement_p75, "
        "quantile(0.75, `rum.vital.inp`) if (`rum.vital.inp`:*) as inp_p75, "
        "max(_time) as last_seen, "
        "values(`rum.environment`) as environment, "
        "values(`rum.release`) as release, "
        "values(`rum.sdk.version`) as sdk_version"
    )


def catalog_spark_query(tenant_id: str, apps: list[str], step: timedelta) -> str:
    base = rum_apps_filter(tenant_id, apps)
    bucket = _time_bucket(step)
    return f'{base} "rum.event.type":view | stats by (`rum.application`, {bucket}) count() as views'


def overview_country_query(tenant_id: str, application: str) -> str:
    base = rum_apps_filter(tenant_id, [application])
    return f'{base} "rum.event.type":view | stats by (`geo.country.iso_code`) ' "count() as views, count_uniq(`rum.session.key`) as sessions"


def overview_facet_query(tenant_id: str, application: str, field: str) -> str:
    if field not in _OVERVIEW_FACETS:
        raise ValueError(f"unsupported overview facet: {field}")
    base = rum_apps_filter(tenant_id, [application])
    return f'{base} "{field}":* | stats by (`{field}`) ' 'count() if ("rum.event.type":view) as views, ' "count_uniq(`rum.session.key`) as sessions"


def overview_device_query(tenant_id: str, application: str) -> str:
    base = rum_apps_filter(tenant_id, [application])
    return (
        f"{base} | stats "
        f"count_uniq(`rum.session.key`) if ({_MOBILE_UA}) as mobile, "
        'count_uniq(`rum.session.key`) if ("user_agent.original":*) as sessions'
    )


def map_catalog_health(
    rows: list[dict],
    spark_rows: list[dict],
    enabled_apps: list[str],
    start: datetime,
    end: datetime,
    buckets: int,
) -> tuple[list[dict], dict[str, list[float]]]:
    found = {_text(row, "rum.application"): row for row in rows}
    out = []
    for app in enabled_apps:
        src = found.get(app) or {}
        sessions = int(_num(src, "sessions"))
        errored = int(_num(src, "errored_sessions"))
        seen = _parse_time(_text(src, "last_seen"))
        out.append(
            {
                "application": app,
                "sessions": sessions,
                "views": int(_num(src, "views")),
                "errors": int(_num(src, "errors")),
                "lcpP75": _prefer_positive(src, "lcp_measurement_p75", "lcp_p75"),
                "inpP75": _prefer_positive(src, "inp_measurement_p75", "inp_p75"),
                "errorRate": clamp_unit(errored / sessions) if sessions else 0.0,
                "environment": sample_text(src, "environment"),
                "release": sample_text(src, "release"),
                "sdkVersion": sample_text(src, "sdk_version"),
                "lastSeenMs": int(seen.timestamp() * 1000) if seen else 0,
            }
        )
    return out, _catalog_sparks(spark_rows, enabled_apps, start, end, buckets)


def map_named_counts(rows: list[dict], source_key: str, out_key: str) -> list[dict]:
    return [
        {
            out_key: _text(row, source_key),
            "views": int(_num(row, "views")),
            "sessions": int(_num(row, "sessions")),
        }
        for row in rows
    ]


def map_device_counts(rows: list[dict]) -> dict:
    row = rows[0] if rows else {}
    sessions = int(_num(row, "sessions"))
    mobile = int(_num(row, "mobile"))
    if mobile > sessions:
        mobile = sessions
    return {"mobile": mobile, "desktop": max(0, sessions - mobile)}


def _prefer_positive(row: dict, primary: str, fallback: str) -> float:
    primary_value = _num(row, primary)
    if primary_value > 0:
        return primary_value
    return _num(row, fallback)


def _catalog_sparks(
    rows: list[dict],
    enabled_apps: list[str],
    start: datetime,
    end: datetime,
    buckets: int,
) -> dict[str, list[float]]:
    n = max(buckets, 1)
    sparks = {app: [0.0] * n for app in enabled_apps}
    width = end - start
    if width.total_seconds() <= 0:
        width = timedelta(hours=1)
    origin = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    for row in rows:
        series = sparks.get(_text(row, "rum.application"))
        if series is None:
            continue
        seen = _parse_time(_text(row, "_time"))
        if seen is None:
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        idx = int((seen - origin) / width * n)
        if idx >= n:
            idx = n - 1
        if idx >= 0:
            series[idx] += float(_num(row, "views"))
    return sparks
