"""LogsQL pushdown, replay scan, and alert read-failure behavior."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from apps.rum.services.control import MemoryControl
from apps.rum.services.evaluator import AlertEvaluator
from apps.rum.services.logsql_stats import (
    ERROR_SORTS,
    SESSION_SORTS,
    error_detail_query,
    error_list_query,
    journey_stats_query,
    map_error_issue,
    map_session_row,
    map_session_summary,
    release_first_issue_query,
    sample_text,
    session_page_query,
    view_stats_query,
)
from apps.rum.services.monitors import MemoryEventStore, MemoryPolicyStore
from apps.rum.services.notify import MemoryNotifier
from apps.rum.services.replay import MemoryReplayIndex
from apps.rum.services.sessions import SessionsService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.victoria_analytics import VictoriaAnalytics
from apps.rum.services.victoria_client import LogRows, VictoriaClient


class FakeVictoria:
    def __init__(self, rows=None):
        self.queries: list[tuple[str, int]] = []
        self.rows = rows if rows is not None else LogRows()

    def query_logs(self, query, start, end, limit=0):
        self.queries.append((query, limit))
        return self.rows


def _opts(**extra):
    now = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    base = {
        "from": now - timedelta(hours=1),
        "to": now,
        "applications": ["storefront"],
        "traffic": "all",
        "orderBy": "impact",
        "limit": 20,
        "offset": 40,
    }
    base.update(extra)
    return base


def test_session_query_contains_stats_sort_offset_limit_and_prefix():
    opts = _opts(orderBy="errors", sessionIdPrefix="abc", offset=40, limit=20)
    query = session_page_query("core", opts)
    assert "stats by" in query
    assert "count()" in query
    assert "count_uniq(" in query
    assert "min(_time)" in query
    assert "max(_time)" in query
    assert SESSION_SORTS["errors"] in query
    assert "offset 40" in query
    assert "limit 20" in query
    assert '"abc"*' in query
    assert '"rum.session.key":"abc"*' in query or '"rum.session.key":"abc"*' in query.replace(" ", "")
    assert "rum_apps" not in query
    assert '"tenant.id":"core"' in query
    assert '"rum.application":in("storefront")' in query


def test_error_sort_mapping_and_empty_apps_do_not_query():
    query = error_list_query("core", _opts(orderBy="relevance", release="1.2.3"))
    assert ERROR_SORTS["relevance"] in query
    assert "sort by (count desc, duration desc, start_time desc)" in query
    assert '"rum.release":"1.2.3"' in query
    client = FakeVictoria()
    page = VictoriaAnalytics(client).list_sessions("core", _opts(applications=[]))
    assert page["sessions"] == []
    assert client.queries == []


def test_analytics_sends_session_stats_query():
    now = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    client = FakeVictoria(
        LogRows(
            [
                {
                    "rum.application": "storefront",
                    "rum.session.key": "abc123",
                    "event_count": "4",
                    "error_count": "1",
                    "start_time": now.isoformat().replace("+00:00", "Z"),
                    "end_time": now.isoformat().replace("+00:00", "Z"),
                }
            ]
        )
    )
    page = VictoriaAnalytics(client).list_sessions(
        "core",
        _opts(orderBy="duration", sessionIdPrefix="ab", limit=10, offset=0),
    )
    assert page["sessions"][0]["sessionId"] == "abc123"
    sent = client.queries[0][0]
    assert "stats by" in sent
    assert SESSION_SORTS["duration"] in sent
    assert "offset 0" in sent
    assert "limit 10" in sent
    assert '"ab"*' in sent


def test_journey_filters_by_session_key_or_id_and_marks_truncation():
    now = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
    stamp = now.isoformat().replace("+00:00", "Z")

    class JourneyClient:
        def __init__(self):
            self.queries = []

        def query_logs(self, query, start, end, limit=0):
            self.queries.append(query)
            if "| stats" in query:
                return LogRows([{"event_count": "1", "start_time": stamp, "end_time": stamp}])
            rows = LogRows(
                [
                    {
                        "_time": stamp,
                        "rum.application": "storefront",
                        "rum.session.id": "sess-9",
                        "rum.event.type": "view",
                        "rum.view.name": "/pay",
                    }
                ]
            )
            rows.truncated = True
            return rows

    client = JourneyClient()
    journey = VictoriaAnalytics(client).session_journey(
        "core",
        "storefront",
        "sess-9",
        {"from": now - timedelta(minutes=5), "to": now},
    )
    assert journey["session"]["sessionId"] == "sess-9"
    assert journey["views"][0]["viewName"] == "/pay"
    assert journey["truncated"] is True
    assert all('("rum.session.key":"sess-9" OR "rum.session.id":"sess-9")' in query for query in client.queries)


def test_journey_missing_only_when_filtered_stats_are_empty():
    now = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)

    class EmptyClient:
        def query_logs(self, query, start, end, limit=0):
            return LogRows()

    journey = VictoriaAnalytics(EmptyClient()).session_journey(
        "core",
        "storefront",
        "missing",
        {"from": now - timedelta(minutes=5), "to": now},
    )
    assert journey["session"] == {}
    assert journey["views"] == []


def test_replay_scan_chunks_and_stops_at_cap_without_total():
    class ChunkAnalytics:
        def available(self):
            return True

        def __init__(self):
            self.calls = []

        def list_sessions(self, tenant_id, opts):
            self.calls.append((opts["offset"], opts["limit"], opts["orderBy"]))
            offset = opts["offset"]
            return {
                "sessions": [
                    {"application": "checkout", "sessionId": f"s{offset + i}", "errorCount": 0}
                    for i in range(opts["limit"])
                ]
            }

    analytics = ChunkAnalytics()
    replay = MemoryReplayIndex()
    service = SessionsService(control=MemoryControl(), analytics=analytics, replay_index=replay)
    service.settings = RumRuntimeSettings(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )
    service._resolve_applications = lambda actor, requested: (["checkout"], None)  # noqa: SLF001
    page = service.list_sessions("tester", {"range": "1h", "hasReplay": "1", "limit": "1", "orderBy": "start"})
    assert page["replayScanTruncated"] is True
    assert "summary" not in page
    assert analytics.calls[0] == (0, 200, "start")
    assert analytics.calls[-1][0] == 1800
    assert sum(call[1] for call in analytics.calls) == 2000


def test_replay_scan_returns_ready_sessions_before_the_cap():
    class ChunkAnalytics:
        def available(self):
            return True

        def list_sessions(self, tenant_id, opts):
            return {
                "sessions": [
                    {"application": "checkout", "sessionId": "ready-1", "errorCount": 1},
                    {"application": "checkout", "sessionId": "plain", "errorCount": 0},
                    {"application": "checkout", "sessionId": "ready-2", "errorCount": 0},
                ]
            }

    replay = MemoryReplayIndex()
    replay.mark_ready("checkout", "ready-1")
    replay.mark_ready("checkout", "ready-2")
    service = SessionsService(control=MemoryControl(), analytics=ChunkAnalytics(), replay_index=replay)
    service.settings = RumRuntimeSettings(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )
    service._resolve_applications = lambda actor, requested: (["checkout"], None)  # noqa: SLF001
    page = service.list_sessions("tester", {"range": "1h", "hasReplay": "true", "limit": "2"})
    assert [row["sessionId"] for row in page["sessions"]] == ["ready-1", "ready-2"]
    assert page["replayScanTruncated"] is False
    assert page["summary"]["total"] == 2


def test_query_exposes_truncated_when_body_or_row_limit_is_hit(monkeypatch):
    import apps.rum.services.victoria_client as victoria_client

    body = b'{"a":"1"}\n{"a":"2"}\n'

    class Response:
        status = 200

        def read(self, n):
            return body[:n]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(victoria_client, "urlopen", lambda req, timeout=0: Response())
    monkeypatch.setattr(victoria_client, "_MAX_RESPONSE_BYTES", 8)
    client = VictoriaClient(logs_endpoint="http://victoria.example.test", traces_endpoint="http://victoria.example.test")
    rows = client.query_logs("stats count()", None, None, limit=1)
    assert rows.truncated is True

    monkeypatch.setattr(victoria_client, "_MAX_RESPONSE_BYTES", 8 << 20)
    exact = client.query_logs("stats count()", None, None, limit=2)
    assert len(exact) == 2
    assert exact.truncated is True
    short = client.query_logs("stats count()", None, None, limit=5)
    assert short.truncated is False


def test_alert_read_failure_skips_without_changing_state(caplog):
    secret = "rum-alert-payload-sentinel-9f3c"
    policies = MemoryPolicyStore()
    policy = policies.save(
        {
            "id": "policy-7",
            "enabled": True,
            "application": "checkout",
            "metric": "error_rate",
            "comparator": ">=",
            "warnThreshold": 0.1,
            "criticalThreshold": 0.2,
            "forDurationSec": 60,
            "noDataAfter": 0,
            "evaluationWindowMinutes": 15,
            "organizations": [10],
            "notificationTargets": [],
        }
    )
    events = MemoryEventStore()
    notifier = MemoryNotifier()

    class Boom:
        def available(self):
            return True

        def monitor_metric(self, tenant_id, opts):
            raise RuntimeError(secret)

    now = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
    with caplog.at_level(logging.WARNING, logger="rum"):
        result = AlertEvaluator(
            policies=policies,
            events=events,
            analytics=Boom(),
            notifier=notifier,
            now=lambda: now,
        ).evaluate_all()
    assert result["failed"] == 1
    assert result["fired"] == 0
    saved = policies.get(policy["id"])
    assert saved["lastEvaluationResult"] == "failed"
    assert saved["evaluationCursor"] == ""
    assert events.list_page(1, 20)[1] == 0
    assert notifier.sent == []
    assert caplog.records
    record = caplog.records[-1]
    assert record.msg == "rum alert metric read skipped policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == ("policy-7", "monitor_metric", "RuntimeError")
    rendered = record.getMessage()
    assert "policy-7" in rendered
    assert "failed_stage=monitor_metric" in rendered
    assert "error_type=RuntimeError" in rendered
    assert secret not in rendered
    assert secret not in caplog.text


def test_monitor_metric_zero_is_an_empty_window_not_a_failure():
    class ZeroAnalytics:
        def available(self):
            return True

        def monitor_metric(self, tenant_id, opts):
            return 0.0

    policies = MemoryPolicyStore()
    policy = policies.save(
        {
            "id": "policy-8",
            "enabled": True,
            "application": "checkout",
            "metric": "error_rate",
            "comparator": ">=",
            "warnThreshold": 0.1,
            "criticalThreshold": 0.2,
            "forDurationSec": 0,
            "noDataAfter": 0,
            "evaluationWindowMinutes": 15,
            "organizations": [10],
            "notificationTargets": [],
        }
    )
    events = MemoryEventStore()
    moment = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
    result = AlertEvaluator(
        policies=policies,
        events=events,
        analytics=ZeroAnalytics(),
        notifier=MemoryNotifier(),
        now=lambda: moment,
    ).evaluate_policy(policy["id"], moment)
    assert result == "none"
    assert policies.get(policy["id"])["lastEvaluationResult"] == "ok"
    assert events.list_page(1, 20)[1] == 0


@pytest.mark.parametrize(
    ("order", "fragment"),
    [
        ("start", "sort by (start_time desc)"),
        ("errors", "sort by (error_count desc, start_time desc)"),
        ("duration", "sort by (duration desc, start_time desc)"),
        ("impact", "sort by (error_count desc, duration desc, start_time desc)"),
    ],
)
def test_session_order_mapping(order, fragment):
    assert fragment in session_page_query("core", _opts(orderBy=order))


def test_stats_queries_use_v138_functions():
    opts = _opts()
    queries = [
        session_page_query("core", opts),
        error_list_query("core", opts),
        error_detail_query("core", "fp-1", opts),
        journey_stats_query("core", "storefront", "abc"),
        view_stats_query("core", opts),
        release_first_issue_query("core", opts),
    ]
    for query in queries:
        assert "any(" not in query
        assert ":(," not in query
    view = queries[4]
    assert "`rum.vital.lcp`:<=2500" in view
    assert "`rum.vital.lcp`:>2500 AND `rum.vital.lcp`:<=4000" in view
    assert "`rum.vital.lcp`:>4000" in view
    assert "values(`user_agent.original`)" in queries[0]


def test_sample_text_reads_one_values_element():
    row = map_session_row(
        {
            "rum.application": "storefront",
            "rum.session.key": "abc",
            "user_agent": '["Mozilla/5.0", "Other"]',
            "entry_route": '["/home", "/cart"]',
            "country": "[]",
            "city": "not-json[",
            "release": "1.2.3",
        }
    )
    assert row["userAgent"] == "Mozilla/5.0"
    assert row["entryRoute"] == "/home"
    assert row["geoCountry"] == ""
    assert row["geoCity"] == "not-json["
    assert row["release"] == "1.2.3"
    issue = map_error_issue(
        {
            "rum.error.fingerprint": "fp",
            "message": '["Error: a", "Error: a again"]',
            "error_type": "Error",
            "application": "storefront",
            "count": "2",
        }
    )
    assert issue["sampleMessage"] == "Error: a"
    assert issue["normalizedMessage"] == "Error: a"
    assert issue["errorType"] == "Error"
    assert issue["application"] == "storefront"
    assert sample_text({"release": ["1.2.3", ""]}, "release") == "1.2.3"


def test_session_summary_converts_logsql_nanoseconds_to_milliseconds():
    summary = map_session_summary({"total": "8", "errored": "1", "median": "232403000064"})
    assert summary["total"] == 8
    assert summary["errored"] == 1
    assert summary["medianDurationMs"] == 232403
    assert map_session_summary({"total": "0", "errored": "0", "median": "0"})["medianDurationMs"] == 0
