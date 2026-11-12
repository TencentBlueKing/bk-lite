"""Web Vitals 告警在聚合起点覆盖窗口时改读聚合库。

会话数和错误会话率仍读 VictoriaLogs。聚合库失败只跳过这一轮判定，不触发、不恢复。
"""

import logging
import traceback
from datetime import UTC, datetime, timedelta

import pytest

from apps.core.aggregate_promql import AggregateMetricsUnavailable
from apps.core.logger import SafeLogException
from apps.rum.services.aggregate_reads import AggregateRumReader
from apps.rum.services.alert_runtime import RumAlertRuntime
from apps.rum.services.alert_store import MemoryEventStore, MemoryPolicyStore
from apps.rum.services.control import MemoryControl
from apps.rum.services.monitors import MonitorsService
from apps.rum.services.victoria_analytics import VictoriaAnalytics

WHEN = datetime(2026, 11, 10, 9, 0, 30, tzinfo=UTC)
# 09:00:30 对齐到 09:00:00，再留出 10 秒刷出周期（见下方 fixture）。
ALIGNED = datetime(2026, 11, 10, 8, 59, 50, tzinfo=UTC)
# 15 分钟窗口的 increase 起点。早于它就还没被聚合覆盖。
LOOKBACK = datetime(2026, 11, 10, 8, 44, 50, tzinfo=UTC)
ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)
SELECTOR = 'tenant_id="core",rum_application="checkout",rum_traffic_class!~"bot|synthetic|crawler"'
VITALS = {
    "lcp_p75": "rum_web_vital_lcp_milliseconds_bucket",
    "inp_p75": "rum_web_vital_inp_milliseconds_bucket",
    "fcp_p75": "rum_web_vital_fcp_milliseconds_bucket",
    "ttfb_p75": "rum_web_vital_ttfb_milliseconds_bucket",
    "cls_p75": "rum_web_vital_cls_bucket",
}


@pytest.fixture(autouse=True)
def _ten_second_flush(monkeypatch):
    # 时间点按 10 秒刷出周期构造；默认值由 core 的刷出间隔测试锁定。
    monkeypatch.setenv("RUM_AGG_BATCH_TIMEOUT", "10s")


def _p75(metric: str, seconds: int, selector: str = SELECTOR) -> str:
    return "histogram_quantile(0.75, sum by (le) " f"(increase({metric}{{{selector}}}[{seconds}s])))"


class Prom:
    def __init__(self, result=None, *, available=True, error=None):
        self.available = available
        self.error = error
        self.instant_result = [] if result is None else result
        self.range_result = []
        self.instant = []
        self.ranges = []

    def query_instant(self, expression, *, at):
        self.instant.append((expression, at))
        if self.error is not None:
            raise self.error
        if callable(self.instant_result):
            return self.instant_result(expression)
        return self.instant_result

    def query_range(self, expression, *, start, end, step_seconds):
        self.ranges.append((expression, start, end, step_seconds))
        if self.error is not None:
            raise self.error
        return self.range_result


class Logs:
    def __init__(self, rows=None, *, error=None):
        self.rows = [] if rows is None else rows
        self.error = error
        self.queries = []

    def query_logs(self, query, start, end, limit=0):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.rows


def _analytics(prom, logs, *, origin=ORIGIN, when=WHEN):
    reader = AggregateRumReader(prom, origin_at=lambda: origin, clock=lambda: when)
    return VictoriaAnalytics(logs, aggregate=reader)


def _opts(metric, *, minutes=15, **extra):
    opts = {
        "application": "checkout",
        "metric": metric,
        "from": WHEN - timedelta(minutes=minutes),
        "to": WHEN,
    }
    opts.update(extra)
    return opts


def _sample(raw):
    return [{"metric": {"le": "+Inf"}, "value": [1, raw]}]


def _policy(policies, **overrides):
    body = {
        "enabled": True,
        "application": "checkout",
        "metric": "lcp_p75",
        "comparator": ">=",
        "warnThreshold": 2500,
        "criticalThreshold": 4000,
        "forDurationSec": 0,
        "noDataAfter": 3,
        "evaluationWindowMinutes": 15,
        "organizations": [10],
        "notificationTargets": [],
        "consecutiveHits": 2,
        "consecutiveRecoveries": 4,
        "consecutiveNoData": 0,
    }
    body.update(overrides)
    return policies.save(body)


def _open(events, policy_id, *, value=2400.0):
    alert = events.create_alert(
        {
            "policyId": policy_id,
            "application": "checkout",
            "metric": "lcp_p75",
            "status": "active",
            "currentValue": value,
            "severity": "warning",
            "organizations": [10],
            "handlers": [],
            "noData": False,
            "startedAt": "2026-11-01T00:00:00Z",
            "lastEventAt": "2026-11-01T00:00:00Z",
        }
    )
    events.add_event(
        {
            "alertId": alert["id"],
            "action": "triggered",
            "occurredAt": alert["startedAt"],
            "severity": "warning",
            "value": value,
            "organizations": [10],
            "content": {"actor": "system", "action": "triggered", "noData": False},
        }
    )
    return alert


def _runtime(analytics, policies, events):
    return RumAlertRuntime(policies=policies, alerts=events, analytics=analytics, now=lambda: WHEN, tenant_id="core")


@pytest.mark.parametrize(
    ("metric", "series", "raw", "expected"),
    [
        ("lcp_p75", VITALS["lcp_p75"], "2400", 2400.0),
        ("inp_p75", VITALS["inp_p75"], "180", 180.0),
        ("fcp_p75", VITALS["fcp_p75"], "900", 900.0),
        ("ttfb_p75", VITALS["ttfb_p75"], "0", 0.0),
        ("cls_p75", VITALS["cls_p75"], "0.08", 0.08),
    ],
)
def test_each_vital_reads_p75_from_the_aggregate(metric, series, raw, expected):
    prom = Prom(_sample(raw))
    logs = Logs(error=AssertionError("victoria logs scanned"))
    value = _analytics(prom, logs).monitor_metric("core", _opts(metric))

    assert value == expected
    assert prom.instant == [(_p75(series, 900), ALIGNED)]
    assert logs.queries == []


def test_missing_vital_samples_are_no_data_and_zero_is_a_value():
    empty = Prom([])
    logs = Logs(error=AssertionError("victoria logs scanned"))
    assert _analytics(empty, logs).monitor_metric("core", _opts("lcp_p75")) is None

    nan = Prom(_sample("NaN"))
    assert _analytics(nan, logs).monitor_metric("core", _opts("cls_p75")) is None

    zero = Prom(_sample("0"))
    assert _analytics(zero, logs).monitor_metric("core", _opts("cls_p75")) == 0.0
    assert logs.queries == []


@pytest.mark.parametrize("minutes", [5, 15, 60])
def test_increase_window_follows_the_policy_and_ends_on_the_flushed_minute(minutes):
    prom = Prom(_sample("2400"))
    logs = Logs(error=AssertionError("victoria logs scanned"))
    value = _analytics(prom, logs).monitor_metric("core", _opts("lcp_p75", minutes=minutes))

    assert value == 2400.0
    assert prom.instant == [(_p75(VITALS["lcp_p75"], minutes * 60), ALIGNED)]


@pytest.mark.parametrize(
    ("origin", "available", "rows", "expected"),
    [
        (LOOKBACK, True, [{"value": "7"}], 2400.0),
        (LOOKBACK + timedelta(seconds=1), True, [{"value": "7"}], 7.0),
        (None, True, [], None),
        (LOOKBACK, False, [{"value": "7"}], 7.0),
    ],
)
def test_uncovered_or_unconfigured_windows_keep_the_log_result(origin, available, rows, expected):
    covered = expected == 2400.0
    prom = Prom(
        _sample("2400"),
        available=available,
        error=None if covered else RuntimeError("aggregate-should-not-run"),
    )
    logs = Logs(rows, error=AssertionError("victoria logs scanned") if covered else None)
    value = _analytics(prom, logs, origin=origin).monitor_metric("core", _opts("lcp_p75"))

    assert value == expected
    assert bool(prom.instant) is covered
    assert bool(logs.queries) is not covered


def test_alert_selector_defaults_to_visitors_and_escapes_labels():
    app = 'shop"\nout'
    tenant = 'ac"\nme'
    prom = Prom(_sample("10"))
    logs = Logs(error=AssertionError("victoria logs scanned"))
    opts = _opts("inp_p75", application=app)
    value = _analytics(prom, logs).monitor_metric(tenant, opts)

    assert value == 10.0
    expression, at = prom.instant[0]
    assert at == ALIGNED
    assert expression == _p75(
        VITALS["inp_p75"],
        900,
        'tenant_id="ac\\"\\nme",rum_application="shop\\"\\nout",rum_traffic_class!~"bot|synthetic|crawler"',
    )
    assert "\n" not in expression
    assert "rum_environment=" not in expression
    assert "rum_aggregate_route=" not in expression
    assert "shard" not in expression

    for traffic, fragment in (
        ("all", None),
        ("automated", 'rum_traffic_class=~"bot|synthetic|crawler"'),
        ("human", 'rum_traffic_class="human"'),
        ('bo\nt"', 'rum_traffic_class="bo\\nt\\""'),
    ):
        client = Prom(_sample("10"))
        _analytics(client, Logs()).monitor_metric("core", _opts("lcp_p75", traffic=traffic))
        text = client.instant[0][0]
        if fragment is None:
            assert "rum_traffic_class" not in text
        else:
            assert fragment in text
        assert "\n" not in text


def test_aggregate_read_failure_does_not_fire_recover_or_scan_logs(caplog):
    secret = "promql-body-sentinel-6c1e"
    prom = Prom(error=RuntimeError(secret))
    logs = Logs([{"value": "5000"}])
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    policy = _policy(policies, noDataAfter=1)
    alert = _open(events, policy["id"])
    with caplog.at_level(logging.WARNING, logger="rum"):
        action = _runtime(_analytics(prom, logs), policies, events).evaluate_policy(policy["id"], WHEN)

    saved = policies.get(policy["id"])
    assert action == "failed"
    assert saved["lastEvaluationResult"] == "failed"
    assert saved["evaluationCursor"] == ""
    assert saved["lastFailedAt"] == "2026-11-10T09:00:30Z"
    assert saved["consecutiveHits"] == 2
    assert saved["consecutiveRecoveries"] == 4
    assert saved["consecutiveNoData"] == 0
    kept = events.get_alert(alert["id"])
    assert kept["status"] == "active"
    assert kept["currentValue"] == 2400.0
    assert [item["action"] for item in events.list_events(alert["id"])] == ["triggered"]
    assert logs.queries == []
    assert caplog.records
    record = caplog.records[-1]
    assert record.msg == "rum alert metric read skipped policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (policy["id"], "monitor_metric", "RuntimeError")
    rendered = record.getMessage()
    assert policy["id"] in rendered
    assert "failed_stage=monitor_metric" in rendered
    assert "error_type=RuntimeError" in rendered
    assert secret not in rendered
    assert secret not in caplog.text
    assert record.exc_info[0] is SafeLogException
    assert str(record.exc_info[1]) == "RuntimeError"
    assert record.exc_info[2] is prom.error.__traceback__
    assert str(prom.error) == secret
    frames = traceback.extract_tb(record.exc_info[2])
    assert any(frame.name == "query_instant" for frame in frames)
    formatted = logging.Formatter().format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert secret not in formatted


def test_empty_vital_follows_no_data_and_zero_can_recover():
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    quiet = _policy(policies, id="quiet", noDataAfter=1)
    held = _policy(policies, id="held")
    open_alert = _open(events, held["id"])
    logs = Logs(error=AssertionError("victoria logs scanned"))

    none_action = _runtime(_analytics(Prom([]), logs), policies, events).evaluate_policy(quiet["id"], WHEN)
    assert none_action == "fired"
    opened = events.active_for_policy(quiet["id"])
    assert opened["currentValue"] is None
    assert opened["noData"] is True

    hold_action = _runtime(_analytics(Prom([]), logs), policies, events).evaluate_policy(held["id"], WHEN)
    assert hold_action == "none"
    assert events.get_alert(open_alert["id"])["status"] == "active"
    assert events.get_alert(open_alert["id"])["currentValue"] == 2400.0
    assert policies.get(held["id"])["consecutiveNoData"] == 1
    assert policies.get(held["id"])["lastEvaluationResult"] == "ok"

    zero_action = _runtime(_analytics(Prom(_sample("0")), logs), policies, events).evaluate_policy(held["id"], WHEN + timedelta(minutes=1))
    assert zero_action == "recovered"
    assert events.get_alert(open_alert["id"])["status"] == "recovered"
    assert events.get_alert(open_alert["id"])["currentValue"] == 0.0


def test_origin_gap_still_fires_from_the_log_value():
    prom = Prom(error=RuntimeError("aggregate-should-not-run"))
    logs = Logs([{"value": "5000"}])
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    policy = _policy(policies, noDataAfter=0, consecutiveHits=0, consecutiveRecoveries=0)
    action = _runtime(_analytics(prom, logs, origin=LOOKBACK + timedelta(seconds=1)), policies, events).evaluate_policy(policy["id"], WHEN)

    assert action == "fired"
    alert = events.active_for_policy(policy["id"])
    assert alert["currentValue"] == 5000.0
    assert alert["noData"] is False
    assert "quantile(0.75, `rum.vital.lcp`)" in logs.queries[0]
    assert prom.instant == []


def test_session_alerts_keep_reading_victoria_logs():
    prom = Prom(_sample("999"), error=RuntimeError("aggregate-should-not-run"))
    logs = Logs([{"value": "0", "sessions": "0", "errored": "0"}])
    analytics = _analytics(prom, logs)
    policies = MemoryPolicyStore()
    events = MemoryEventStore()
    sessions = _policy(
        policies,
        id="sessions",
        metric="session_count",
        warnThreshold=1,
        criticalThreshold=2,
        consecutiveHits=0,
        consecutiveRecoveries=0,
    )
    errors = _policy(
        policies,
        id="errors",
        metric="error_rate",
        warnThreshold=0.1,
        criticalThreshold=0.2,
        consecutiveHits=0,
        consecutiveRecoveries=0,
    )
    runtime = _runtime(analytics, policies, events)

    assert runtime.evaluate_policy(sessions["id"], WHEN) == "none"
    assert policies.get(sessions["id"])["lastEvaluationResult"] == "ok"
    assert policies.get(sessions["id"])["evaluationCursor"] == "2026-11-10T09:00:00+00:00"
    assert "count_uniq(`rum.session.key`) as value" in logs.queries[0]
    assert "rum.vital" not in logs.queries[0]

    assert runtime.evaluate_policy(errors["id"], WHEN + timedelta(minutes=1)) == "none"
    assert policies.get(errors["id"])["lastEvaluationResult"] == "ok"
    assert policies.get(errors["id"])["consecutiveNoData"] == 1
    assert "errored" in logs.queries[1]
    assert prom.instant == []
    assert prom.ranges == []


def test_alert_trend_reads_aggregate_percentiles_and_keeps_zero():
    start = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 11, 10, 0, 16, tzinfo=UTC)
    prom = Prom()
    prom.range_result = [
        {
            "metric": {"le": "+Inf"},
            "values": [[start.timestamp() + 480, "2400"], [start.timestamp() + 900, "NaN"], [start.timestamp() + 960, "0"]],
        }
    ]
    logs = Logs(error=AssertionError("victoria logs scanned"))
    points = _analytics(prom, logs, when=end).metric_series(
        "core",
        {"application": "checkout", "metric": "fcp_p75", "from": start, "to": end, "points": 2},
    )

    assert [point["value"] for point in points] == [2400.0, 0.0]
    assert points[0]["atMs"] == int(start.timestamp() * 1000)
    assert points[1]["atMs"] == int((start + timedelta(minutes=8)).timestamp() * 1000)
    expression, range_start, range_end, step = prom.ranges[0]
    assert expression == _p75(VITALS["fcp_p75"], 480)
    assert range_start == start + timedelta(minutes=8)
    assert range_end == datetime(2026, 11, 10, 0, 15, 50, tzinfo=UTC)
    assert step == 480
    assert logs.queries == []


def test_trend_points_stay_in_their_step_when_the_window_does_not_divide_evenly():
    start = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    end = start + timedelta(seconds=1000)
    prom = Prom()
    prom.range_result = [
        {
            "metric": {"le": "+Inf"},
            "values": [[start.timestamp() + 333, "100"], [start.timestamp() + 666, "200"]],
        }
    ]
    logs = Logs(error=AssertionError("victoria logs scanned"))
    points = _analytics(prom, logs, when=end).metric_series(
        "core",
        {"application": "checkout", "metric": "lcp_p75", "from": start, "to": end, "points": 3},
    )

    assert [point["value"] for point in points] == [100.0, 200.0, None]
    assert prom.ranges[0][1] == start + timedelta(seconds=333)
    assert prom.ranges[0][3] == 333
    assert logs.queries == []


def test_alert_trend_failure_clears_the_chart_and_keeps_the_stored_event(caplog):
    secret = "promql-body-sentinel-6c1e"
    prom = Prom(error=AggregateMetricsUnavailable(secret))
    logs = Logs([{"value": "1", "_time": "2026-11-10T00:00:00Z"}])
    analytics = _analytics(prom, logs, origin=datetime(2020, 1, 1, tzinfo=UTC), when=datetime.now(UTC))
    events = MemoryEventStore()
    alert = _open(events, "policy-old", value=2400.0)
    service = MonitorsService(control=MemoryControl(), analytics=analytics, policies=MemoryPolicyStore(), events=events)

    with caplog.at_level(logging.WARNING, logger="rum"):
        detail = service.get_alert_event(alert["id"], visible_orgs={10})

    assert detail["trend"] == []
    assert detail["alert"]["currentValue"] == 2400.0
    assert detail["events"][0]["value"] == 2400.0
    assert detail["events"][0]["action"] == "triggered"
    assert logs.queries == []
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.msg == "event=rum_aggregate_read_failed tenant_id=%s failed_stage=%s error_type=%s"
    assert record.args == ("core", "alert_trend", "AggregateMetricsUnavailable")
    assert record.getMessage() == "event=rum_aggregate_read_failed tenant_id=core failed_stage=alert_trend error_type=AggregateMetricsUnavailable"
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is prom.error.__traceback__
    frames = traceback.extract_tb(record.exc_info[2])
    assert any(frame.name == "query_range" for frame in frames)
    formatted = logging.Formatter().format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert secret not in record.getMessage()
    assert secret not in formatted
    assert secret not in caplog.text


def test_stored_vital_evidence_stays_while_the_trend_reads_aggregate():
    prom = Prom()
    prom.range_result = [{"metric": {"le": "+Inf"}, "values": [[datetime.now(UTC).timestamp() - 60, "100"]]}]
    logs = Logs(error=AssertionError("victoria logs scanned"))
    analytics = _analytics(prom, logs, origin=datetime(2020, 1, 1, tzinfo=UTC), when=datetime.now(UTC))
    events = MemoryEventStore()
    alert = _open(events, "policy-old", value=2400.0)
    service = MonitorsService(control=MemoryControl(), analytics=analytics, policies=MemoryPolicyStore(), events=events)

    detail = service.get_alert_event(alert["id"], visible_orgs={10})

    assert detail["alert"]["currentValue"] == 2400.0
    assert detail["events"][0]["value"] == 2400.0
    assert any(point["value"] == 100 for point in detail["trend"])
    assert logs.queries == []
