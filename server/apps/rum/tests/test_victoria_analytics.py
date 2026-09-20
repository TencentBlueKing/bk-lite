"""LogsQL / Victoria analytics parity tests vs Haro plugins/ops/server/rum/victoria."""

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


def test_rum_apps_filter_matches_haro_contract():
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
