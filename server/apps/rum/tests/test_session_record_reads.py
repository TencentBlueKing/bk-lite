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
            rows.append({key: value for key, value in item.items() if not str(key).startswith("_")})
        return LogRows(rows)

    def record_calls(self):
        return [call for call in self.calls if "max(`rum.session.event_count`)" in call["query"]]

    def live_calls(self):
        return [
            call
            for call in self.calls
            if "count() as event_count" in call["query"] and "sort by" not in call["query"] and "count() as total" not in call["query"]
        ]


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
    assert '"geo.country.iso_code":' not in client.record_calls()[-1]["query"]
    assert '"geo.country.iso_code":' in client.live_calls()[-1]["query"]

    by_route = VictoriaAnalytics(client).list_sessions("core", _opts(now, route="/pay"))
    assert {row["sessionId"] for row in by_route["sessions"]} == {"entry", "open"}
    assert '"rum.view.name":' not in client.record_calls()[-1]["query"]
    assert '"rum.context.route":' in client.live_calls()[-1]["query"]

    by_user = VictoriaAnalytics(client).list_sessions("core", _opts(now, userId="bob"))
    assert [row["sessionId"] for row in by_user["sessions"]] == ["open"]
    assert '"rum.user.id":' not in client.record_calls()[-1]["query"]
    assert '"rum.user.id":"bob"' in client.live_calls()[-1]["query"]


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


def test_catalog_keeps_raw_counts_when_the_merged_sessions_are_truncated():
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
    client.truncate_records = True
    rows, _sparks = VictoriaAnalytics(client).applications_page("core", now - timedelta(hours=1), now, ["storefront"])
    assert rows[0]["sessions"] == 99
    assert rows[0]["errorRate"] == pytest.approx(1.0)
    assert rows[0]["views"] == 7


def test_alert_session_metrics_still_read_raw_events():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    opts = {"application": "storefront", "from": now - timedelta(minutes=15), "to": now}
    session_count = monitor_metric_query("core", {**opts, "metric": "session_count"})
    error_rate = monitor_metric_query("core", {**opts, "metric": "error_rate"})
    assert "count_uniq(`rum.session.key`)" in session_count
    assert "session_end" not in session_count
    assert "count_uniq(`rum.session.key`)" in error_rate
    assert "session_end" not in error_rate
