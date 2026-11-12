"""Session list, summary, and trend read session_end records.

The scripted client is the VictoriaLogs stand-in. It does not interpret LogsQL.
It honors the time bounds and the filters the query actually asks for, and it
returns duplicate record rows so the server must collapse them.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from apps.rum.services import session_records
from apps.rum.services.logsql_stats import monitor_metric_query
from apps.rum.services.victoria_analytics import VictoriaAnalytics
from apps.rum.services.victoria_client import LogRows, aggregate_sessions


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


class ScriptedLogs:
    """Return fixture rows only when the query asks for the matching slice."""

    def __init__(self, *, epoch, records=(), live=(), legacy=(), summary=None, fail_probes=0):
        self.epoch = epoch
        self.records = list(records)
        self.live = list(live)
        self.legacy = list(legacy)
        self.summary = summary or {"total": "1", "errored": "0", "median": "0"}
        self.fail_probes = fail_probes
        self.probes = 0
        self.calls: list[dict] = []
        self.truncate_live = False
        self.truncate_records = False

    def query_logs(self, query, start, end, limit=0):
        self.calls.append({"query": query, "start": start, "end": end, "limit": limit})
        if "min(_time) as first_seen" in query:
            self.probes += 1
            if self.probes <= self.fail_probes:
                leaked = "sentinel-vl-body-9f3c"
                self.probe_error = RuntimeError(leaked)
                raise self.probe_error
            if self.epoch is None:
                return LogRows()
            return LogRows([{"first_seen": _iso(self.epoch)}])
        if '"rum.session.key":in(' in query:
            return self._present(query, start, end)
        if "floor((start_time -" in query:
            return self._trend_buckets(query, start, end)
        if "count() as sessions" in query and "session_end" in query:
            return self._app_counts(query, start, end)
        if "count() as total" in query and "max(`rum.session.event_count`)" in query:
            return LogRows([self._record_summary(query, start, end)])
        if "max(`rum.session.event_count`)" in query:
            rows = self._bounded(self.records, query, start, end)
            if self.truncate_records:
                rows.truncated = True
            return rows
        if "count() as total" in query:
            return LogRows([dict(self.summary)])
        if "sort by" in query:
            return self._bounded(self.legacy, query, start, end)
        if "count() as event_count" in query:
            rows = self._bounded(self.live, query, start, end)
            if self.truncate_live:
                rows.truncated = True
            return rows
        return LogRows()

    def _present(self, query, start, end) -> LogRows:
        wanted = set(_in_keys(query))
        rows = []
        seen = set()
        for item in self.records:
            at = item.get("_at")
            if at is not None and start is not None and at < start:
                continue
            if at is not None and end is not None and at > end:
                continue
            key = item.get("rum.session.key")
            pair = (item.get("rum.application"), key)
            if key in wanted and pair not in seen:
                seen.add(pair)
                rows.append({"rum.application": item.get("rum.application"), "rum.session.key": key, "copies": "1"})
        return LogRows(rows)

    def _record_summary(self, query, start, end) -> dict:
        grouped: dict[str, dict] = {}
        for item in self._bounded(self.records, query, start, end):
            key = item.get("rum.session.key") or ""
            current = grouped.setdefault(key, {"error": 0, "duration": 0})
            current["error"] = max(current["error"], int(item.get("error_count") or 0))
            current["duration"] = max(current["duration"], int(float(item.get("duration_ms") or 0)))
        durations = sorted(item["duration"] for item in grouped.values())
        errored = sum(1 for item in grouped.values() if item["error"] > 0)
        median = durations[len(durations) // 2] if durations else 0
        return {"total": str(len(grouped)), "errored": str(errored), "median": str(median)}

    def _app_counts(self, query, start, end) -> LogRows:
        grouped: dict[str, dict] = {}
        for item in self._bounded(self.records, query, start, end):
            app = item.get("rum.application") or ""
            key = item.get("rum.session.key") or ""
            current = grouped.setdefault(app, {})
            session = current.setdefault(key, 0)
            current[key] = max(session, int(item.get("error_count") or 0))
        return LogRows(
            [
                {
                    "rum.application": app,
                    "sessions": str(len(sessions)),
                    "errored": str(sum(1 for error in sessions.values() if error > 0)),
                }
                for app, sessions in grouped.items()
            ]
        )

    def _trend_buckets(self, query, start, end) -> LogRows:
        origin = int(query.split("floor((start_time - ", 1)[1].split(")", 1)[0].split("/", 1)[0].strip())
        step = int(query.split(") / ", 1)[1].split(")", 1)[0].strip())
        buckets: dict[int, list[int]] = {}
        seen = set()
        for item in self._bounded(self.records, query, start, end):
            key = item.get("rum.session.key")
            if key in seen:
                continue
            seen.add(key)
            index = (int(item.get("start_time") or 0) - origin) // step
            total, errored = buckets.setdefault(index, [0, 0])
            total += 1
            if int(item.get("error_count") or 0) > 0:
                errored += 1
            buckets[index] = [total, errored]
        return LogRows([{"bucket": str(index), "total": str(total), "errored": str(errored)} for index, (total, errored) in buckets.items()])

    def _bounded(self, source, query, start, end) -> LogRows:
        marker = "`rum.session.started_at_ms`:<="
        bound = None
        if marker in query:
            bound = int(query.split(marker, 1)[1].split("|", 1)[0].strip())
        visitors = 'NOT "rum.traffic.class":in("bot","synthetic","crawler")' in query
        rows = []
        for item in source:
            at = item.get("_at")
            if at is not None and start is not None and at < start:
                continue
            if at is not None and end is not None and at > end:
                continue
            if bound is not None and int(item.get("_start_ms") or 0) > bound:
                continue
            if visitors and item.get("traffic_class") in {"bot", "synthetic", "crawler"}:
                continue
            country = _quoted_filter(query, "geo.country.iso_code")
            if country is not None and item.get("country") != country:
                continue
            route = _quoted_filter(query, "rum.view.name")
            if route is not None and route not in {item.get("entry_route"), item.get("context_route")}:
                continue
            user_id = _quoted_filter(query, "rum.user.id")
            if user_id is not None and item.get("user_id") != user_id:
                continue
            if _error_filter(query) and int(item.get("error_count") or 0) <= 0:
                continue
            idle_after = _idle_after(query)
            if idle_after is not None and at is not None and at < idle_after:
                continue
            public = {key: value for key, value in item.items() if not str(key).startswith("_")}
            if item.get("_at") is not None and item.get("_start_ms") is not None:
                public["duration_ms"] = str(int(item["_at"].timestamp() * 1000) - int(item["_start_ms"]))
            rows.append(public)
        return LogRows(rows)

    def record_calls(self):
        return [call for call in self.calls if "max(`rum.session.event_count`)" in call["query"]]

    def live_calls(self):
        return [
            call
            for call in self.calls
            if "count() as event_count" in call["query"] and "sort by" not in call["query"] and "count() as total" not in call["query"]
        ]


def _present_calls(client: ScriptedLogs):
    return [call for call in client.calls if '"rum.session.key":in(' in call["query"]]


def _in_keys(query: str) -> list[str]:
    body = query.split('"rum.session.key":in(', 1)[1].split(")", 1)[0]
    return json.loads(f"[{body}]")


def _error_filter(query: str) -> bool:
    return "`rum.session.error_count`:>0" in query or "| filter error_count:>0" in query


def _idle_after(query: str):
    marker = "filter end_time:>="
    if marker not in query:
        return None
    raw = query.split(marker, 1)[1].split("|", 1)[0].strip()
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _quoted_filter(query: str, field: str):
    marker = f'"{field}":'
    if marker not in query:
        return None
    rest = query.split(marker, 1)[1]
    try:
        value, _end = json.JSONDecoder().raw_decode(rest)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) else None


def _record(session_id, *, at, start, event_count, view_count, error_count, traffic="human", route="/pay", user_id=""):
    return {
        "_at": at,
        "_start_ms": _ms(start),
        "rum.application": "storefront",
        "rum.session.key": session_id,
        "event_count": str(event_count),
        "view_count": str(view_count),
        "error_count": str(error_count),
        "start_time": str(_ms(start)),
        "end_time": _iso(at),
        "entry_route": route,
        "traffic_class": traffic,
        "user_id": user_id,
    }


def _live(
    session_id,
    *,
    at,
    event_count,
    view_count,
    error_count,
    traffic="human",
    user_agent="",
    route="/live",
    context_route="",
    country="",
    user_id="",
):
    return {
        "_at": at,
        "rum.application": "storefront",
        "rum.session.key": session_id,
        "event_count": str(event_count),
        "view_count": str(view_count),
        "error_count": str(error_count),
        "start_time": _iso(at),
        "end_time": _iso(at),
        "entry_route": route,
        "context_route": context_route,
        "country": country,
        "traffic_class": traffic,
        "user_agent": user_agent,
        "user_id": user_id,
    }


def _opts(now, **extra):
    base = {
        "from": now - timedelta(hours=24),
        "to": now,
        "applications": ["storefront"],
        "traffic": "all",
        "orderBy": "start",
        "limit": 20,
        "offset": 0,
    }
    base.update(extra)
    return base


def _by_id(page):
    return {row["sessionId"]: row for row in page["sessions"]}


def test_merged_sessions_match_raw_events_without_double_counting():
    """Ended sessions keep the record's max counts; the recent raw copy is not added again."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old_at = now - timedelta(hours=10)
    dup_at = now - timedelta(minutes=20)
    live_at = now - timedelta(minutes=5)

    def event(when, session_id, event_type, event_id, route):
        return {
            "time": when,
            "application": "storefront",
            "sessionId": session_id,
            "eventType": event_type,
            "eventId": event_id,
            "route": route,
        }

    events = [
        event(old_at, "old", "view", "o1", "/old"),
        event(old_at + timedelta(seconds=1), "old", "view", "o2", "/old"),
        event(dup_at, "dup", "view", "d1", "/pay"),
        event(dup_at + timedelta(seconds=1), "dup", "view", "d2", "/pay"),
        event(dup_at + timedelta(seconds=2), "dup", "error", "d3", "/pay"),
        event(live_at, "live", "view", "l1", "/live"),
        event(live_at + timedelta(seconds=1), "live", "view", "l2", "/live"),
        event(live_at + timedelta(seconds=2), "live", "view", "l3", "/live"),
    ]
    client = ScriptedLogs(
        epoch=now - timedelta(days=30),
        records=[
            _record("old", at=old_at + timedelta(seconds=1), start=old_at, event_count=2, view_count=2, error_count=0, route="/old"),
            _record("dup", at=dup_at + timedelta(seconds=2), start=dup_at, event_count=3, view_count=2, error_count=1),
            _record("dup", at=dup_at + timedelta(seconds=2), start=dup_at, event_count=1, view_count=1, error_count=0),
        ],
        live=[
            _live("dup", at=dup_at + timedelta(seconds=2), event_count=1, view_count=1, error_count=0),
            _live("live", at=live_at, event_count=3, view_count=3, error_count=0, user_agent="Phone"),
        ],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, limit=20))
    oracle = aggregate_sessions(events, {"traffic": "all", "limit": 50})
    got = {(row["sessionId"], row["eventCount"], row["viewCount"], row["errorCount"]) for row in page["sessions"]}
    want = {(row["sessionId"], row["eventCount"], row["viewCount"], row["errorCount"]) for row in oracle["sessions"]}
    assert got == want
    assert len(page["sessions"]) == 3
    assert page["summary"]["total"] == 3
    assert page["summary"]["errored"] == 1
    assert page["summary"]["errored"] / page["summary"]["total"] == pytest.approx(1 / 3)
    rows = _by_id(page)
    assert rows["dup"]["eventCount"] == 3
    assert rows["dup"]["errorCount"] == 1
    assert rows["live"]["userAgent"] == "Phone"
    assert rows["dup"]["userAgent"] == ""
    record_call = client.record_calls()[0]
    assert record_call["start"] == now - timedelta(hours=24)
    assert record_call["end"] - now == timedelta(hours=4, minutes=15)
    assert f"`rum.session.started_at_ms`:<={_ms(now)}" in record_call["query"]
    assert "max(`rum.session.view_count`) as view_count" in record_call["query"]
    assert "max(`rum.session.error_count`) as error_count" in record_call["query"]
    assert "count() as event_count" not in record_call["query"]
    live_call = client.live_calls()[0]
    assert abs((live_call["start"] - (now - timedelta(hours=4))).total_seconds()) < 30
    assert live_call["end"] == now
    assert 'NOT "rum.event.type":session_end' in live_call["query"]
    assert live_call["limit"] > 0
    assert "limit " in live_call["query"]


def test_duplicate_record_counts_take_the_max_of_each_field():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=10)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record("mix", at=at, start=at - timedelta(minutes=1), event_count=10, view_count=4, error_count=1),
            _record("mix", at=at, start=at - timedelta(minutes=1), event_count=4, view_count=1, error_count=3),
        ],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, limit=10))
    assert len(page["sessions"]) == 1
    row = page["sessions"][0]
    assert row["sessionId"] == "mix"
    assert row["eventCount"] == 10
    assert row["viewCount"] == 4
    assert row["errorCount"] == 3


def test_in_progress_session_appears_and_session_ended_after_the_window_is_kept():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    started = now - timedelta(minutes=1)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record("overlaps", at=now + timedelta(hours=2), start=started, event_count=5, view_count=2, error_count=0),
            _record("after", at=now + timedelta(hours=2), start=now + timedelta(minutes=1), event_count=9, view_count=1, error_count=0),
        ],
        live=[_live("open", at=now - timedelta(minutes=2), event_count=2, view_count=2, error_count=0)],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, **{"from": now - timedelta(hours=1)}))
    assert _by_id(page).keys() == {"overlaps", "open"}
    assert _by_id(page)["overlaps"]["eventCount"] == 5


def test_sort_page_and_error_filter_use_the_merged_set():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = ScriptedLogs(
        epoch=now - timedelta(days=2),
        records=[
            _record("old", at=now - timedelta(hours=10), start=now - timedelta(hours=10), event_count=2, view_count=2, error_count=0),
            _record("dup", at=now - timedelta(minutes=20), start=now - timedelta(minutes=30), event_count=3, view_count=1, error_count=2),
        ],
        live=[_live("live", at=now - timedelta(minutes=5), event_count=1, view_count=1, error_count=0)],
    )
    opts = _opts(now, orderBy="start", offset=1, limit=1)
    page = VictoriaAnalytics(client).list_sessions("core", opts)
    assert [row["sessionId"] for row in page["sessions"]] == ["dup"]
    assert page["summary"]["total"] == 3

    errors = VictoriaAnalytics(client).list_sessions("core", _opts(now, hasError=True, orderBy="errors", limit=10))
    assert [row["sessionId"] for row in errors["sessions"]] == ["dup"]
    assert errors["summary"]["total"] == 1
    assert errors["summary"]["errored"] == 1
    assert errors["summary"]["replayed"] == 0


def test_visitor_traffic_filter_drops_crawler_records_and_live_sessions():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=8)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record("human", at=at, start=at, event_count=2, view_count=1, error_count=0, traffic="human"),
            _record("bot", at=at, start=at, event_count=4, view_count=1, error_count=0, traffic="crawler"),
        ],
        live=[_live("spy", at=at, event_count=1, view_count=1, error_count=0, traffic="synthetic")],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, traffic="visitors"))
    assert [row["sessionId"] for row in page["sessions"]] == ["human"]
    assert 'NOT "rum.traffic.class":in("bot","synthetic","crawler")' in client.record_calls()[0]["query"]
    assert 'NOT "rum.traffic.class":in("bot","synthetic","crawler")' in client.live_calls()[0]["query"]


def test_ended_sessions_stay_out_when_the_record_cannot_match_the_filter():
    """A country, later route, or later user on raw events must not resurrect an ended session."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=10)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record("ended", at=at, start=at, event_count=4, view_count=2, error_count=0, route="/home", user_id="alice"),
            _record("entry", at=at, start=at, event_count=3, view_count=1, error_count=0, route="/pay", user_id="alice"),
        ],
        live=[
            _live(
                "ended",
                at=at,
                event_count=1,
                view_count=1,
                error_count=0,
                route="/home",
                context_route="/pay",
                country="US",
                user_id="bob",
            ),
            _live("open", at=now - timedelta(minutes=2), event_count=1, view_count=1, error_count=0, route="/pay", country="US", user_id="bob"),
        ],
    )
    by_country = VictoriaAnalytics(client).list_sessions("core", _opts(now, country="US"))
    assert [row["sessionId"] for row in by_country["sessions"]] == ["open"]
    assert client.record_calls() == []
    assert '"geo.country.iso_code":' in client.live_calls()[-1]["query"]
    present = _present_calls(client)[-1]
    assert "geo.country" not in present["query"]
    assert '"rum.session.key":in(' in present["query"]
    assert "ended" in present["query"]

    by_route = VictoriaAnalytics(client).list_sessions("core", _opts(now, route="/pay"))
    assert {row["sessionId"] for row in by_route["sessions"]} == {"entry", "open"}
    assert '"rum.view.name":"/pay"' in client.record_calls()[-1]["query"]
    assert "rum.context.route" not in client.record_calls()[-1]["query"]
    assert '"rum.context.route":' in client.live_calls()[-1]["query"]
    assert "rum.view.name" not in _present_calls(client)[-1]["query"]

    by_user = VictoriaAnalytics(client).list_sessions("core", _opts(now, userId="bob"))
    assert [row["sessionId"] for row in by_user["sessions"]] == ["open"]
    assert '"rum.user.id":"bob"' in client.record_calls()[-1]["query"]
    assert '"rum.user.id":"bob"' in client.live_calls()[-1]["query"]
    assert "rum.user.id" not in _present_calls(client)[-1]["query"]


def test_window_starting_before_record_epoch_uses_raw_events():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    window_from = now - timedelta(hours=3)
    client = ScriptedLogs(
        epoch=now - timedelta(hours=1),
        records=[
            _record(
                "from-record",
                at=now - timedelta(minutes=10),
                start=now - timedelta(minutes=10),
                event_count=8,
                view_count=1,
                error_count=0,
            )
        ],
        legacy=[
            {
                "_at": now - timedelta(minutes=30),
                "rum.application": "storefront",
                "rum.session.key": "from-raw",
                "event_count": "4",
                "error_count": "0",
                "view_count": "4",
                "start_time": _iso(now - timedelta(minutes=30)),
                "end_time": _iso(now - timedelta(minutes=30)),
            }
        ],
        summary={"total": "1", "errored": "0", "median": "0"},
    )
    page = VictoriaAnalytics(client).list_sessions(
        "core",
        _opts(now, **{"from": window_from, "orderBy": "impact", "limit": 10, "offset": 0}),
    )
    assert [row["sessionId"] for row in page["sessions"]] == ["from-raw"]
    assert page["summary"]["total"] == 1
    assert client.record_calls() == []
    legacy = next(call for call in client.calls if "sort by" in call["query"])
    assert legacy["start"] == window_from
    assert legacy["end"] == now
    assert 'NOT "rum.event.type":session_end' in legacy["query"]
    assert "offset 0" in legacy["query"]
    assert "limit 10" in legacy["query"]


def test_trend_counts_each_session_once_including_errors():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(minutes=30)
    # Middles of the 5-minute buckets, so a 1ms timestamp skew cannot cross a boundary.
    record_at = start + timedelta(minutes=22)
    live_at = start + timedelta(minutes=12)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[_record("ended", at=record_at, start=record_at, event_count=2, view_count=1, error_count=1)],
        live=[
            _live("ended", at=record_at, event_count=1, view_count=1, error_count=1),
            _live("open", at=live_at, event_count=1, view_count=1, error_count=0),
        ],
    )
    trend = VictoriaAnalytics(client).session_trend(
        "core",
        {"from": start, "to": now, "applications": ["storefront"], "traffic": "all"},
    )
    assert sum(point["total"] for point in trend["points"]) == 2
    assert sum(point["errored"] for point in trend["points"]) == 1
    assert trend["points"][4]["total"] == 1
    assert trend["points"][4]["errored"] == 1
    assert trend["points"][2]["total"] == 1
    assert trend["points"][2]["errored"] == 0


def test_live_group_truncation_is_visible():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=3)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        live=[_live("open", at=at, event_count=1, view_count=1, error_count=0)],
    )
    client.truncate_live = True
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now))
    assert page["truncated"] is True
    assert [row["sessionId"] for row in page["sessions"]] == ["open"]


def test_epoch_probe_is_cached_and_a_failed_probe_falls_back_without_leaking_the_body(settings, caplog):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rum-session-epoch-probe",
        }
    }
    from django.core.cache import cache

    cache.clear()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=5)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[_record("kept", at=at, start=at, event_count=2, view_count=1, error_count=0)],
        legacy=[
            {
                "_at": at,
                "rum.application": "storefront",
                "rum.session.key": "raw-only",
                "event_count": "1",
                "view_count": "1",
                "error_count": "0",
                "start_time": _iso(at),
                "end_time": _iso(at),
            }
        ],
        fail_probes=1,
    )
    opts = _opts(now)
    caplog.set_level(logging.WARNING, logger="rum")
    first = VictoriaAnalytics(client).list_sessions("core", opts)
    assert [row["sessionId"] for row in first["sessions"]] == ["raw-only"]
    rum_traces = [record for record in caplog.records if record.name == "rum" and record.exc_info]
    assert len(rum_traces) == 1
    warning = rum_traces[0]
    assert warning.levelno == logging.WARNING
    assert warning.msg == ("rum session record epoch probe failed failed_stage=session_record_epoch tenant_id=%s error_type=%s")
    assert warning.args == ("core", "RuntimeError")
    rendered = warning.getMessage()
    formatted = logging.Formatter().format(warning)
    assert "sentinel-vl-body-9f3c" not in rendered
    assert "sentinel-vl-body-9f3c" not in formatted
    assert "RuntimeError" in rendered
    exc_type, exc_value, exc_tb = warning.exc_info
    assert exc_type is RuntimeError
    assert str(exc_value) == "RuntimeError"
    assert exc_value is not client.probe_error
    assert str(client.probe_error) == "sentinel-vl-body-9f3c"
    assert exc_tb is client.probe_error.__traceback__
    assert first["sessions"][0]["eventCount"] == 1

    second = VictoriaAnalytics(client).list_sessions("core", opts)
    assert [row["sessionId"] for row in second["sessions"]] == ["kept"]
    third = VictoriaAnalytics(client).list_sessions("core", opts)
    assert [row["sessionId"] for row in third["sessions"]] == ["kept"]
    assert client.probes == 2


def test_catalog_error_rate_uses_merged_sessions_not_raw_event_counts():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=6)

    class CatalogLogs(ScriptedLogs):
        def query_logs(self, query, start, end, limit=0):
            health = "stats by (`rum.application`)" in query and "max(`rum.session.event_count`)" not in query and "_time:" not in query
            if health:
                return LogRows(
                    [
                        {
                            "rum.application": "storefront",
                            "sessions": "99",
                            "views": "7",
                            "errors": "4",
                            "errored_sessions": "99",
                            "lcp_p75": "1800",
                        }
                    ]
                )
            return super().query_logs(query, start, end, limit)

    client = CatalogLogs(
        epoch=now - timedelta(days=3),
        records=[_record("bad", at=at, start=at, event_count=2, view_count=1, error_count=1)],
        live=[_live("open", at=now - timedelta(minutes=2), event_count=1, view_count=1, error_count=0)],
    )
    rows, _sparks = VictoriaAnalytics(client).applications_page("core", now - timedelta(hours=1), now, ["storefront"])
    assert rows[0]["views"] == 7
    assert rows[0]["errors"] == 4
    assert rows[0]["lcpP75"] == 1800.0
    assert rows[0]["sessions"] == 2
    assert rows[0]["errorRate"] == pytest.approx(0.5)


def test_catalog_session_counts_come_from_stats_not_loaded_rows():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=6)

    class CatalogLogs(ScriptedLogs):
        def query_logs(self, query, start, end, limit=0):
            health = "stats by (`rum.application`)" in query and "max(`rum.session.event_count`)" not in query and "_time:" not in query
            if health:
                return LogRows(
                    [
                        {
                            "rum.application": "storefront",
                            "sessions": "99",
                            "views": "7",
                            "errors": "4",
                            "errored_sessions": "99",
                            "lcp_p75": "1800",
                        }
                    ]
                )
            return super().query_logs(query, start, end, limit)

    client = CatalogLogs(
        epoch=now - timedelta(days=3),
        records=[_record("bad", at=at, start=at, event_count=2, view_count=1, error_count=1)],
        live=[_live("open", at=now - timedelta(minutes=2), event_count=1, view_count=1, error_count=0)],
    )
    rows, _sparks = VictoriaAnalytics(client).applications_page("core", now - timedelta(hours=1), now, ["storefront"])
    stats = next(call for call in client.calls if "count() as sessions" in call["query"])
    assert "session_end" in stats["query"]
    assert "max(`rum.session.event_count`)" in stats["query"]
    assert stats["limit"] == 1
    assert "limit 50000" not in stats["query"]
    assert rows[0]["sessions"] == 2
    assert rows[0]["errorRate"] == pytest.approx(0.5)
    assert rows[0]["views"] == 7


def test_record_page_fetches_only_the_merge_window():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    base = now - timedelta(hours=6)
    client = ScriptedLogs(
        epoch=now - timedelta(days=30),
        records=[
            _record(
                f"s{index}",
                at=base + timedelta(minutes=index),
                start=base + timedelta(minutes=index),
                event_count=1,
                view_count=1,
                error_count=0,
            )
            for index in range(30)
        ],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, orderBy="start", offset=10, limit=5))
    assert [row["sessionId"] for row in page["sessions"]] == ["s19", "s18", "s17", "s16", "s15"]
    fetched = next(call for call in client.record_calls() if "sort by" in call["query"])
    assert fetched["limit"] == 15
    assert "limit 15" in fetched["query"]
    assert "50000" not in fetched["query"]
    summary = next(call for call in client.calls if "quantile(0.5, duration)" in call["query"])
    assert summary["limit"] == 1
    assert page["summary"]["total"] == 30


def test_page_merges_ended_and_live_before_slicing():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = ScriptedLogs(
        epoch=now - timedelta(days=2),
        records=[
            _record("older", at=now - timedelta(hours=3), start=now - timedelta(hours=3), event_count=1, view_count=1, error_count=0),
            _record("middle", at=now - timedelta(minutes=20), start=now - timedelta(minutes=25), event_count=2, view_count=1, error_count=0),
        ],
        live=[_live("newest", at=now - timedelta(minutes=5), event_count=1, view_count=1, error_count=0)],
    )
    first = VictoriaAnalytics(client).list_sessions("core", _opts(now, orderBy="start", offset=0, limit=2))
    assert [row["sessionId"] for row in first["sessions"]] == ["newest", "middle"]
    fetched = next(call for call in client.record_calls() if "sort by" in call["query"])
    assert fetched["limit"] == 2
    second = VictoriaAnalytics(client).list_sessions("core", _opts(now, orderBy="start", offset=2, limit=1))
    assert [row["sessionId"] for row in second["sessions"]] == ["older"]


def test_candidate_keys_are_probed_in_batches_and_recorded_ones_drop_out(monkeypatch):
    monkeypatch.setattr(session_records, "_KEY_BATCH", 1)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    at = now - timedelta(minutes=4)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[_record("kept", at=at, start=at, event_count=4, view_count=1, error_count=0)],
        live=[
            _live("kept", at=at, event_count=1, view_count=1, error_count=0),
            _live("open-a", at=at, event_count=1, view_count=1, error_count=0),
            _live("open-b", at=at + timedelta(seconds=1), event_count=1, view_count=1, error_count=0),
        ],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, orderBy="start", limit=10))
    assert {row["sessionId"] for row in page["sessions"]} == {"kept", "open-a", "open-b"}
    assert _by_id(page)["kept"]["eventCount"] == 4
    probes = _present_calls(client)
    assert len(probes) == 3
    assert {tuple(_in_keys(call["query"])) for call in probes} == {("kept",), ("open-a",), ("open-b",)}
    assert all("rum.view.name" not in call["query"] and "geo.country" not in call["query"] for call in probes)


def test_sessions_idle_longer_than_thirty_minutes_wait_for_a_record():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        live=[
            _live("stale", at=now - timedelta(minutes=45), event_count=3, view_count=1, error_count=0),
            _live("open", at=now - timedelta(minutes=2), event_count=1, view_count=1, error_count=0),
        ],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now))
    assert [row["sessionId"] for row in page["sessions"]] == ["open"]
    assert "filter end_time:>=" in client.live_calls()[0]["query"]


def test_trend_counts_the_start_bucket_once():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(minutes=30)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record(
                "spans",
                at=start + timedelta(minutes=16),
                start=start + timedelta(minutes=1),
                event_count=4,
                view_count=2,
                error_count=0,
            )
        ],
        live=[_live("open", at=start + timedelta(minutes=11), event_count=1, view_count=1, error_count=0)],
    )
    trend = VictoriaAnalytics(client).session_trend(
        "core",
        {"from": start, "to": now, "applications": ["storefront"], "traffic": "all"},
    )
    assert trend["points"][0]["total"] == 1
    assert trend["points"][2]["total"] == 1
    assert trend["points"][3]["total"] == 0
    assert sum(point["total"] for point in trend["points"]) == 2
    assert "floor((start_time -" in next(call["query"] for call in client.calls if " as bucket" in call["query"])


def test_median_blends_the_record_quantile_with_live_sessions():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = ScriptedLogs(
        epoch=now - timedelta(days=1),
        records=[
            _record("short", at=now - timedelta(minutes=9), start=now - timedelta(minutes=10), event_count=1, view_count=1, error_count=0),
            _record("long", at=now - timedelta(minutes=10), start=now - timedelta(minutes=20), event_count=1, view_count=1, error_count=0),
        ],
        live=[_live("open", at=now - timedelta(minutes=2), event_count=1, view_count=1, error_count=0)],
    )
    page = VictoriaAnalytics(client).list_sessions("core", _opts(now, limit=10))
    assert page["summary"]["total"] == 3
    assert page["summary"]["medianDurationMs"] == 400000


def test_alert_session_metrics_still_read_raw_events():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    opts = {"application": "storefront", "from": now - timedelta(minutes=15), "to": now}
    session_count = monitor_metric_query("core", {**opts, "metric": "session_count"})
    error_rate = monitor_metric_query("core", {**opts, "metric": "error_rate"})
    assert "count_uniq(`rum.session.key`)" in session_count
    assert "session_end" not in session_count
    assert "count_uniq(`rum.session.key`)" in error_rate
    assert "session_end" not in error_rate
