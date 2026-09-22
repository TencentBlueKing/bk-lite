"""LogsQL / Victoria analytics parity tests vs the upstream RUM query contract."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from apps.rum.services.victoria_analytics import VictoriaAnalytics
from apps.rum.services.victoria_client import funnel_reached, health_from_events, parse_event, rum_apps_filter, session_trend_points


class _VLHandler(BaseHTTPRequestHandler):
    got_query = ""
    rows: list[dict] = []

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/health"):
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if not self.path.endswith("/select/logsql/query"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        for part in body.split("&"):
            if part.startswith("query="):
                from urllib.parse import unquote_plus

                type(self).got_query = unquote_plus(part[len("query=") :])
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for row in type(self).rows:
            self.wfile.write((json.dumps(row) + "\n").encode("utf-8"))


def _serve(rows: list[dict]) -> tuple[HTTPServer, str]:
    _VLHandler.rows = rows
    _VLHandler.got_query = ""
    server = HTTPServer(("127.0.0.1", 0), _VLHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_rum_apps_filter_matches_wire_contract():
    query = rum_apps_filter("core", ["storefront"])
    assert '"rum.event.type":*' in query
    assert '"tenant.id":"core"' in query
    assert '"rum.application":in("storefront")' in query


def test_applications_page_queries_logsql():
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "_time": (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "view",
            "rum.environment": "production",
            "rum.release": "2026.08.18",
            "rum.sdk.version": "1.2.3",
        },
        {
            "_time": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "vital",
            "rum.measurement.lcp": 2400,
        },
        {
            "_time": (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
            "rum.application": "storefront",
            "rum.session.id": "s2",
            "rum.event.type": "error",
        },
    ]
    server, base = _serve(rows)
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base, ping=True)
        assert analytics.available() is True
        page_rows, sparks = analytics.applications_page("core", now - timedelta(minutes=10), now, ["storefront"])
        assert '"rum.event.type":*' in _VLHandler.got_query
        assert '"tenant.id":"core"' in _VLHandler.got_query
        assert '"rum.application":in("storefront")' in _VLHandler.got_query
        assert len(page_rows) == 1
        assert page_rows[0]["application"] == "storefront"
        assert page_rows[0]["sessions"] == 2
        assert page_rows[0]["views"] == 1
        assert page_rows[0]["errors"] == 1
        assert page_rows[0]["lcpP75"] == 2400.0
        assert page_rows[0]["sdkVersion"] == "1.2.3"
        assert len(sparks["storefront"]) == 12
    finally:
        server.shutdown()


def test_health_from_synthetic_events_fills_contract_fields():
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        {
            "time": now,
            "application": "storefront",
            "sessionId": "s1",
            "eventType": "view",
            "environment": "production",
            "release": "r1",
            "sdkVersion": "1.2.3",
        },
        {
            "time": now + timedelta(seconds=1),
            "application": "storefront",
            "sessionId": "s1",
            "eventType": "vital",
            "vitalName": "lcp",
            "vitalValue": 2400,
        },
        {
            "time": now + timedelta(seconds=2),
            "application": "storefront",
            "sessionId": "s2",
            "eventType": "error",
        },
        {
            "time": now + timedelta(seconds=3),
            "application": "storefront",
            "sessionId": "s2",
            "eventType": "vital",
            "vitalName": "inp",
            "vitalValue": 180,
        },
    ]
    rows, sparks = health_from_events(events, ["storefront"], now - timedelta(minutes=1), now + timedelta(minutes=1), 12)
    assert len(rows) == 1
    assert rows[0]["sessions"] == 2
    assert rows[0]["views"] == 1
    assert rows[0]["errors"] == 1
    assert rows[0]["lcpP75"] == 2400.0
    assert rows[0]["inpP75"] == 180.0
    assert abs(rows[0]["errorRate"] - 0.5) < 0.01
    assert len(sparks["storefront"]) == 12


def test_session_trend_keeps_current_partial_bucket_in_7d_window():
    end = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    start = end - timedelta(days=7)
    points = session_trend_points(
        [
            {
                "time": end - timedelta(minutes=10),
                "sessionId": "s-now",
                "eventType": "view",
            }
        ],
        start,
        end,
    )
    assert len(points) == 7
    assert sum(point["total"] for point in points) == 1
    assert points[-1]["total"] == 1


def test_health_sparkline_counts_view_at_window_end():
    start = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    _, sparks = health_from_events(
        [
            {
                "time": end,
                "application": "storefront",
                "sessionId": "s1",
                "eventType": "view",
            }
        ],
        ["storefront"],
        start,
        end,
        7,
    )
    assert sum(sparks["storefront"]) == 1


def test_health_does_not_turn_sessionless_errors_into_errored_sessions():
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        {"time": now, "application": "storefront", "sessionId": "s1", "eventType": "view"},
        {"time": now + timedelta(seconds=1), "application": "storefront", "sessionId": "", "eventType": "error"},
    ]
    rows, _ = health_from_events(events, ["storefront"], now - timedelta(minutes=1), now + timedelta(minutes=1), 12)
    assert rows[0]["sessions"] == 1
    assert rows[0]["errors"] == 1
    assert rows[0]["errorRate"] == 0


def test_list_sessions_excludes_sessionless_ingest_evidence():
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "_time": now.isoformat().replace("+00:00", "Z"),
            "rum.application": "storefront",
            "rum.event.type": "ingest_evidence",
        },
        {
            "_time": now.isoformat().replace("+00:00", "Z"),
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "view",
        },
    ]
    server, base = _serve(rows)
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base)
        page = analytics.list_sessions(
            "core",
            {
                "from": now - timedelta(minutes=1),
                "to": now + timedelta(minutes=1),
                "applications": ["storefront"],
                "traffic": "all",
            },
        )
        assert len(page["sessions"]) == 1
        assert page["sessions"][0]["sessionId"] == "s1"
    finally:
        server.shutdown()


def test_session_journey_formats_event_timestamps():
    """Regression: `_fmt` used `timezone.utc` without importing it → NameError on every journey."""
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    rows = [
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "view",
            "rum.view.name": "/checkout",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "error",
            "rum.error.message": "boom",
        },
    ]
    server, base = _serve(rows)
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base)
        journey = analytics.session_journey(
            "core",
            "storefront",
            "s1",
            {"from": now - timedelta(minutes=1), "to": now + timedelta(minutes=1)},
        )
        assert journey["views"][0]["timestamp"] == "2026-08-18T12:00:00Z"
        assert journey["errors"][0]["timestamp"] == "2026-08-18T12:00:00Z"
        assert '"rum.session.key":"s1"' in _VLHandler.got_query
        assert '"rum.session.id":"s1"' in _VLHandler.got_query
    finally:
        server.shutdown()


def test_empty_application_list_never_queries_tenant_wide():
    """Fail closed: no enabled/requested apps → no LogsQL request at all."""
    server, base = _serve([])
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base)
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        page = analytics.list_sessions(
            "core",
            {"from": now - timedelta(hours=1), "to": now, "applications": [], "traffic": "all"},
        )
        assert page["sessions"] == []
        assert _VLHandler.got_query == ""
    finally:
        server.shutdown()
    try:
        rum_apps_filter("core", [])
        assert False, "expected ValueError for empty application list"
    except ValueError:
        pass


def test_quote_logsql_escapes_backslash_and_quotes():
    from apps.rum.services.victoria_client import quote_logsql

    assert quote_logsql('a"b') == '"a\\"b"'
    assert quote_logsql("a\\b") == '"a\\\\b"'
    # A crafted value cannot close the string and append a second filter.
    assert '" "rum.application"' not in quote_logsql('x" "rum.application":*')


def test_funnel_respects_window_seconds():
    start = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        {"time": start, "application": "storefront", "sessionId": "s1", "eventType": "view", "route": "/a"},
        {
            "time": start + timedelta(minutes=10),
            "application": "storefront",
            "sessionId": "s1",
            "eventType": "view",
            "route": "/b",
        },
    ]
    assert funnel_reached(events, ["/a", "/b"], timedelta(minutes=1)) == [1, 0]
    assert funnel_reached(events, ["/a", "/b"], timedelta(minutes=15)) == [1, 1]


def test_list_views_fills_cwv_device_and_spark_fields():
    """Views table needs INP/CLS/dist/deviceMix/mom — not only LCP P75."""
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")
    rows = [
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "view",
            "rum.view.name": "/cart",
            "user_agent.original": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "vital",
            "rum.view.name": "/cart",
            "rum.measurement.lcp": "1800",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "vital",
            "rum.view.name": "/cart",
            "rum.measurement.inp": "120",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.event.type": "vital",
            "rum.view.name": "/cart",
            "rum.measurement.cls": "0.05",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s2",
            "rum.event.type": "view",
            "rum.view.name": "/cart",
            "user_agent.original": "Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36",
        },
        {
            "_time": stamp,
            "rum.application": "storefront",
            "rum.session.id": "s2",
            "rum.event.type": "vital",
            "rum.view.name": "/cart",
            "rum.measurement.lcp": "5000",
        },
    ]
    server, base = _serve(rows)
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base)
        page = analytics.list_views(
            "core",
            {
                "from": now - timedelta(hours=1),
                "to": now + timedelta(minutes=1),
                "applications": ["storefront"],
                "mode": "route",
                "traffic": "all",
            },
        )
        assert len(page["rows"]) == 1
        row = page["rows"][0]
        assert row["route"] == "/cart"
        assert row["views"] == 2
        assert row["sessions"] == 2
        # Shared percentile uses floor index: sorted([1800, 5000]) @ p75 → 1800.
        assert row["lcpP75"] == 1800.0
        assert row["inpP75"] == 120.0
        assert row["clsP75"] == 0.05
        assert row["dist"]["good"] == 1
        assert row["dist"]["poor"] == 1
        assert row["dist"]["missing"] == 0
        assert row["deviceMix"]["mobile"] == 1
        assert row["deviceMix"]["desktop"] == 1
        assert row["mom"]["hasDelta"] is True
        assert sum(row["mom"]["spark"]) == 2
        assert page["summary"]["inpP75"] == 120.0
    finally:
        server.shutdown()


def test_list_releases_fills_first_seen_users_issues_and_cwv():
    """Release table needs firstSeen / users / newIssues / LCP — not only sessions."""
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    early = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    late = now.isoformat().replace("+00:00", "Z")
    rows = [
        {
            "_time": early,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.user.id": "u1",
            "rum.event.type": "view",
            "rum.release": "dev",
            "rum.view.name": "/",
        },
        {
            "_time": early,
            "rum.application": "storefront",
            "rum.session.id": "s1",
            "rum.user.id": "u1",
            "rum.event.type": "vital",
            "rum.release": "dev",
            "rum.measurement.lcp": "1800",
        },
        {
            "_time": late,
            "rum.application": "storefront",
            "rum.session.id": "s2",
            "rum.user.id": "u2",
            "rum.event.type": "error",
            "rum.release": "dev",
            "rum.error.fingerprint": "fp-checkout",
            "rum.error.message": "CheckoutError: payment declined",
            "rum.error.type": "CheckoutError",
        },
        {
            "_time": late,
            "rum.application": "storefront",
            "rum.session.id": "s2",
            "rum.user.id": "u2",
            "rum.event.type": "error",
            "rum.release": "1.0.0",
            "rum.error.fingerprint": "fp-checkout",
            "rum.error.message": "CheckoutError: payment declined",
            "rum.error.type": "CheckoutError",
        },
        {
            "_time": late,
            "rum.application": "storefront",
            "rum.session.id": "s3",
            "rum.user.id": "u3",
            "rum.event.type": "error",
            "rum.release": "1.0.0",
            "rum.error.fingerprint": "fp-new",
            "rum.error.message": "TypeError: boom",
            "rum.error.type": "TypeError",
        },
    ]
    server, base = _serve(rows)
    try:
        analytics = VictoriaAnalytics.open(logs_endpoint=base, traces_endpoint=base)
        page = analytics.list_releases(
            "core",
            {
                "from": now - timedelta(hours=1),
                "to": now + timedelta(minutes=1),
                "applications": ["storefront"],
                "traffic": "all",
            },
        )
        by_release = {row["release"]: row for row in page["releases"]}
        assert set(by_release) == {"dev", "1.0.0"}
        dev = by_release["dev"]
        assert dev["firstSeen"] == early
        assert dev["affectedUsers"] == 2
        assert dev["affectedSessions"] == 2
        assert dev["errorCount"] == 1
        assert dev["distinctIssues"] == 1
        assert dev["newIssues"] == 1  # fp-checkout first seen on dev
        assert dev["lcpP75"] == 1800.0
        v100 = by_release["1.0.0"]
        assert v100["newIssues"] == 1  # fp-new only
        assert v100["distinctIssues"] == 2
        assert v100["affectedUsers"] == 2
    finally:
        server.shutdown()


def test_parse_event_matches_product_kpi_fields():
    row = parse_event(
        {
            "rum.application": "storefront",
            "rum.session.id": "sess-1",
            "rum.event.type": "view",
            "rum.environment": "production",
            "rum.release": "2026.08.18",
            "_time": datetime(2026, 8, 18, 1, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    assert row["application"] == "storefront"
    assert row["eventType"] == "view"
    assert row["sessionId"] == "sess-1"


def test_parse_event_prefers_product_session_key_for_replay_index():
    row = parse_event(
        {
            "rum.application": "storefront",
            "rum.session.id": "faro-raw-id",
            "rum.session.key": "d334781a5de70001265c68b0f5e7b082",
            "rum.event.type": "view",
            "_time": datetime(2026, 8, 18, 1, 0, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    assert row["sessionId"] == "d334781a5de70001265c68b0f5e7b082"
