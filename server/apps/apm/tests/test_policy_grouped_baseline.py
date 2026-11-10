"""基线历史窗按目标分组后，对比值、判断和证据曲线仍与逐目标查询一致。"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable, TelemetryUniqueSpanLimitExceeded
from apps.apm.models import ApmPolicy, ApmPolicyTargetState
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed
from apps.apm.tests.test_policy_grouped_red import RecordingStore, _assert_same_outcome, _live, _minute, _next_service, _policy, _run_pair, _stamp

pytestmark = pytest.mark.django_db

OFFSET_CASES = (
    ("previous_window", None, timedelta(minutes=1)),
    ("offset_1h", None, timedelta(hours=1)),
    ("offset_24h", None, timedelta(hours=24)),
    ("offset_hours", 3, timedelta(hours=3)),
    ("offset_days", 2, timedelta(days=2)),
)


def _offset_spans(moment, later, offset: timedelta):
    spans = [
        _live(moment - offset, trace_id="pay-base", span_id="pay-base", name="GET /pay", status="ok"),
        _live(moment - offset, trace_id="ok-base", span_id="ok-base", name="GET /ok", status="ok"),
        _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error", duration_ms=400),
        _live(moment, trace_id="ok", span_id="ok", name="GET /ok", duration_ms=50),
        _live(later, trace_id="pay2", span_id="pay2", name="GET /pay", status="ok"),
        _live(later, trace_id="ok2", span_id="ok2", name="GET /ok", status="ok"),
    ]
    if offset != timedelta(minutes=1):
        spans.extend(
            [
                _live(later - offset, trace_id="pay-base-2", span_id="pay-base-2", name="GET /pay", status="ok"),
                _live(later - offset, trace_id="ok-base-2", span_id="ok-base-2", name="GET /ok", status="ok"),
            ]
        )
    return spans


def _offset_policy(mode: str, amount):
    return {
        "endpoints": ["GET /pay", "GET /ok"],
        "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
        "metric_type": ApmPolicy.MetricType.ERROR_RATE,
        "compare_mode": mode,
        "compare_offset_amount": amount,
        "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
    }


@pytest.mark.parametrize(("mode", "amount", "offset"), OFFSET_CASES)
def test_offset_window_grouped_matches_per_target_compare_and_baseline_curve(mode, amount, offset):
    moment = _minute()
    later = moment + timedelta(minutes=1)
    spans = _offset_spans(moment, later, offset)
    grouped, plain, store = _run_pair(
        policy_kwargs=_offset_policy(mode, amount),
        spans_by_minute=[spans, spans],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("service_red") == 0
    # 当前窗一次，历史窗一次；触发和恢复各一轮。
    assert store.calls.count("service_red_grouped") == 4


def test_offset_window_store_calls_do_not_grow_with_target_count():
    moment = _minute()
    counted = []
    for target_count in (3, 30):
        service = _next_service(f"offset-calls-{target_count}")
        spans = []
        for index in range(target_count):
            name = f"GET /{index}"
            spans.append(_live(moment, trace_id=f"c{index}", span_id=f"c{index}", name=name, status="error" if index == 0 else "ok"))
            spans.append(_live(moment - timedelta(minutes=1), trace_id=f"b{index}", span_id=f"b{index}", name=name, status="ok"))
        store = RecordingStore(_stamp(service, spans))
        policy = _policy(
            service,
            endpoint_mode=ApmPolicy.EndpointMode.ALL,
            endpoints=[],
            compare_mode=ApmPolicy.CompareMode.PREVIOUS_WINDOW,
            compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
            thresholds=[{"severity": "error", "comparator": "gt", "value": "0.5"}],
        )
        DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)
        counted.append(
            {
                "service_red": store.calls.count("service_red"),
                "service_red_grouped": store.calls.count("service_red_grouped"),
                "service_endpoints": store.calls.count("service_endpoints"),
            }
        )

    assert counted[0] == counted[1]
    assert counted[0] == {"service_red": 0, "service_red_grouped": 2, "service_endpoints": 1}


def test_two_offset_windows_each_get_one_grouped_read():
    moment = _minute()
    service = _next_service("two-offsets")
    spans = [
        _live(moment - timedelta(hours=1), trace_id="pay-1h", span_id="pay-1h", name="GET /pay", status="ok"),
        _live(moment - timedelta(hours=1), trace_id="ok-1h", span_id="ok-1h", name="GET /ok", status="ok"),
        _live(moment - timedelta(hours=3), trace_id="pay-3h", span_id="pay-3h", name="GET /pay", status="ok"),
        _live(moment - timedelta(hours=3), trace_id="ok-3h", span_id="ok-3h", name="GET /ok", status="ok"),
        _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error", duration_ms=400),
        _live(moment, trace_id="ok", span_id="ok", name="GET /ok", duration_ms=50),
    ]
    store = RecordingStore(_stamp(service, spans))
    plain = RecordingStore(_stamp(service, spans), grouped=False)
    conditions = [
        {
            "ref": "a",
            "role": "regular",
            "metric_type": "error_rate",
            "compare_mode": "offset_1h",
            "compare_value_kind": "delta",
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        },
        {
            "ref": "b",
            "role": "regular",
            "metric_type": "error_rate",
            "compare_mode": "offset_hours",
            "compare_offset_amount": 3,
            "compare_value_kind": "delta",
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        },
    ]
    kwargs = {
        "endpoints": ["GET /pay", "GET /ok"],
        "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
        "compare_mode": ApmPolicy.CompareMode.OFFSET_1H,
        "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        "conditions": conditions,
    }
    grouped_policy = _policy(service, name=f"grouped-{service.name}", **kwargs)
    plain_policy = _policy(service, name=f"plain-{service.name}", **kwargs)
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(grouped_policy.id, evaluated_at=moment)
    DjangoApmPolicyService(plain, InMemoryNotificationDispatcher()).evaluate(plain_policy.id, evaluated_at=moment)

    _assert_same_outcome(grouped_policy.id, plain_policy.id, require_recovery=False)
    assert store.calls.count("service_red") == 0
    # 当前窗、1 小时前、3 小时前各一次。
    assert store.calls.count("service_red_grouped") == 3


def test_http_offset_window_stays_per_target():
    moment = _minute()
    later = moment + timedelta(minutes=1)

    def _http(at, trace_id, route, *, status="ok"):
        return _live(
            at,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="GET",
            status=status,
            attributes={"http.request.method": "GET", "http.route": route, "peer.service": "billing"},
        )

    spans = [
        _http(moment - timedelta(minutes=1), "users-base", "/users"),
        _http(moment - timedelta(minutes=1), "orders-base", "/orders"),
        _http(moment, "users", "/users", status="error"),
        _http(moment, "orders", "/orders", status="error"),
        _http(later, "users2", "/users"),
        _http(later, "orders2", "/orders"),
    ]
    grouped, plain, store = _run_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "http", "system": "billing", "statement": "GET /users"},
                {"channel": "http", "system": "billing", "statement": "GET /orders"},
            ],
            "compare_mode": ApmPolicy.CompareMode.PREVIOUS_WINDOW,
            "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        },
        spans_by_minute=[spans, spans],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red_grouped") == 0
    assert store.calls.count("dependency_red") == 8


def test_database_offset_window_groups_once_per_window():
    moment = _minute()
    later = moment + timedelta(minutes=1)

    def _db(at, trace_id, statement, *, status="ok"):
        return _live(
            at,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="SELECT",
            status=status,
            attributes={"db.system.name": "mysql", "db.statement": statement},
        )

    spans = [
        _db(moment - timedelta(minutes=1), "orders-base", "SELECT orders"),
        _db(moment - timedelta(minutes=1), "users-base", "SELECT users"),
        _db(moment, "orders", "SELECT orders", status="error"),
        _db(moment, "users", "SELECT users"),
        _db(later, "orders2", "SELECT orders"),
        _db(later, "users2", "SELECT users"),
    ]
    grouped, plain, store = _run_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                {"channel": "database", "system": "mysql", "statement": "SELECT users"},
            ],
            "compare_mode": ApmPolicy.CompareMode.PREVIOUS_WINDOW,
            "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        },
        spans_by_minute=[spans, spans],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red") == 0
    assert store.calls.count("dependency_red_grouped") == 4


def test_historical_unique_span_limit_falls_back_without_marking_failure(caplog):
    moment = _minute()
    service = _next_service("history-limit")
    spans = [
        _live(moment, trace_id="a", span_id="a", name="GET /a", status="error"),
        _live(moment, trace_id="b", span_id="b", name="GET /b"),
        _live(moment - timedelta(minutes=1), trace_id="a-base", span_id="a-base", name="GET /a"),
        _live(moment - timedelta(minutes=1), trace_id="b-base", span_id="b-base", name="GET /b"),
    ]
    kwargs = {
        "endpoints": ["GET /a", "GET /b"],
        "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
        "compare_mode": ApmPolicy.CompareMode.PREVIOUS_WINDOW,
        "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
    }

    class LimitHistory(RecordingStore):
        def service_red_grouped(self, query):
            self.calls.append("service_red_grouped")
            if query.ended_at < moment:
                raise TelemetryUniqueSpanLimitExceeded("limit")
            return self.inner.service_red_grouped(query)

    limited = LimitHistory(_stamp(service, spans))
    plain = RecordingStore(_stamp(service, spans), grouped=False)
    limited_policy = _policy(service, name="limited-history", **kwargs)
    plain_policy = _policy(service, name="plain-history", **kwargs)
    caplog.set_level(logging.DEBUG, logger="apm")
    DjangoApmPolicyService(limited, InMemoryNotificationDispatcher()).evaluate(limited_policy.id, evaluated_at=moment)
    DjangoApmPolicyService(plain, InMemoryNotificationDispatcher()).evaluate(plain_policy.id, evaluated_at=moment)

    _assert_same_outcome(limited_policy.id, plain_policy.id, require_recovery=False)
    assert limited.calls.count("service_red_grouped") == 2
    assert limited.calls.count("service_red") == 4
    assert ApmPolicyTargetState.objects.filter(policy=limited_policy, last_failed_at__isnull=False).count() == 0


def test_historical_grouped_failure_marks_every_target():
    moment = _minute()
    service = _next_service("history-down")
    spans = [
        _live(moment, trace_id="a", span_id="a", name="GET /a", status="error"),
        _live(moment, trace_id="b", span_id="b", name="GET /b"),
        _live(moment - timedelta(minutes=1), trace_id="a-base", span_id="a-base", name="GET /a"),
        _live(moment - timedelta(minutes=1), trace_id="b-base", span_id="b-base", name="GET /b"),
    ]

    class HistoryDown(RecordingStore):
        def service_red_grouped(self, query):
            self.calls.append("service_red_grouped")
            if query.ended_at < moment:
                self.error = TelemetryStoreUnavailable("grouped down")
                raise self.error
            return self.inner.service_red_grouped(query)

    store = HistoryDown(_stamp(service, spans))
    policy = _policy(
        service,
        endpoints=["GET /a", "GET /b"],
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        compare_mode=ApmPolicy.CompareMode.PREVIOUS_WINDOW,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.5"}],
    )

    with pytest.raises(TelemetryStoreUnavailable, match="grouped down"):
        DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    states = list(ApmPolicyTargetState.objects.filter(policy=policy))
    assert len(states) == 2
    assert all(state.last_failed_at is not None for state in states)
    assert store.calls.count("service_red") == 0


def test_replay_stays_per_target_and_matches_the_plain_path():
    moment = _minute()
    service = _next_service("replay-offset")
    spans = _offset_spans(moment, moment, timedelta(minutes=1))

    class ReplayStore(RecordingStore):
        def service_red_by_window(self, query, window_minutes):
            self.calls.append("service_red_by_window")
            end = query.ended_at
            step = timedelta(minutes=window_minutes)
            points = []
            for index in range(2):
                error_rate = 0.8 if index == 0 and query.endpoint == "GET /pay" else 0.0
                points.append((end - step * index, ServiceRed(10, error_rate, 10, 10, request_count=30)))
            return tuple(points)

    grouped_store = ReplayStore(_stamp(service, spans))
    plain_store = ReplayStore(_stamp(service, spans), grouped=False)
    kwargs = _offset_policy(ApmPolicy.CompareMode.PREVIOUS_WINDOW, None)
    grouped_policy = _policy(service, name=f"grouped-replay-{service.name}", **kwargs)
    plain_policy = _policy(service, name=f"plain-replay-{service.name}", **kwargs)
    runner = DjangoApmPolicyService(grouped_store, InMemoryNotificationDispatcher())
    plain_runner = DjangoApmPolicyService(plain_store, InMemoryNotificationDispatcher())
    grouped = runner.dry_run(grouped_policy, evaluated_at=moment, replay_hours=24)
    plain = plain_runner.dry_run(plain_policy, evaluated_at=moment, replay_hours=24)

    assert [item["replay"] for item in grouped["items"]] == [item["replay"] for item in plain["items"]]
    assert any(item["replay"]["hits"] for item in grouped["items"])
    assert grouped_store.calls.count("service_red_by_window") == plain_store.calls.count("service_red_by_window") == 2
    assert grouped_store.calls.count("service_red") == 0


class DayRecordingStore(RecordingStore):
    def __init__(self, spans, *, grouped: bool = True, unique_span_limit: int | None = None):
        super().__init__(spans, grouped=grouped, unique_span_limit=unique_span_limit)
        if not grouped:
            self.service_red_grouped_by_day = None
            self.dependency_red_grouped_by_day = None

    def service_red_grouped_by_day(self, query, windows):
        self.calls.append("service_red_grouped_by_day")
        return self.inner.service_red_grouped_by_day(query, windows)

    def dependency_red_grouped_by_day(self, query, windows):
        self.calls.append("dependency_red_grouped_by_day")
        return self.inner.dependency_red_grouped_by_day(query, windows)


def _run_day_pair(*, policy_kwargs, spans, moments):
    service = _next_service("baseline-days")
    grouped_store = DayRecordingStore([])
    plain_store = DayRecordingStore([], grouped=False)
    grouped_policy = _policy(service, name=f"grouped-{service.name}", **policy_kwargs)
    plain_policy = _policy(service, name=f"plain-{service.name}", **policy_kwargs)
    grouped_runner = DjangoApmPolicyService(grouped_store, InMemoryNotificationDispatcher())
    plain_runner = DjangoApmPolicyService(plain_store, InMemoryNotificationDispatcher())
    stamped = _stamp(service, spans)
    for moment in moments:
        grouped_store.spans = stamped
        plain_store.spans = list(stamped)
        grouped_runner.evaluate(grouped_policy.id, evaluated_at=moment)
        plain_runner.evaluate(plain_policy.id, evaluated_at=moment)
    return grouped_policy, plain_policy, grouped_store


def _p95_span(moment, *, days: int, name: str, duration: float, trace: str):
    return _live(
        moment - timedelta(days=days),
        trace_id=trace,
        span_id=trace,
        name=name,
        duration_ms=duration,
        status="ok",
    )


def _baseline_day_spans(moment, later):
    spans = []
    for anchor, suffix in ((moment, "a"), (later, "b")):
        for day, duration in ((1, 100), (2, 200), (3, 300)):
            spans.append(_p95_span(anchor, days=day, name="GET /hot", duration=duration, trace=f"hot-{suffix}-{day}"))
            spans.append(_p95_span(anchor, days=day, name="GET /flat", duration=100, trace=f"flat-{suffix}-{day}"))
    spans.extend(
        [
            _p95_span(moment, days=0, name="GET /hot", duration=400, trace="hot-now"),
            _p95_span(moment, days=0, name="GET /flat", duration=100, trace="flat-now"),
            _p95_span(later, days=0, name="GET /hot", duration=50, trace="hot-later"),
            _p95_span(later, days=0, name="GET /flat", duration=100, trace="flat-later"),
        ]
    )
    return spans


def _baseline_policy(**updates):
    values = {
        "endpoints": ["GET /hot", "GET /flat"],
        "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
        "metric_type": ApmPolicy.MetricType.P95,
        "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
        "compare_offset_amount": 3,
        "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "slow_threshold_ms": None,
        "apdex_threshold_ms": None,
    }
    values.update(updates)
    return values


def test_baseline_days_grouped_by_target_matches_per_target_mean_and_curve():
    moment = _minute()
    later = moment + timedelta(minutes=1)
    grouped, plain, store = _run_day_pair(
        policy_kwargs=_baseline_policy(),
        spans=_baseline_day_spans(moment, later),
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped_by_day") == 2
    assert store.calls.count("service_red_grouped") == 2


def test_sigma_grouped_by_day_matches_per_target_judgment():
    moment = _minute()
    spans = []
    for day, duration in ((1, 90), (2, 100), (3, 110)):
        spans.append(_p95_span(moment, days=day, name="GET /hot", duration=duration, trace=f"hot-{day}"))
        spans.append(_p95_span(moment, days=day, name="GET /flat", duration=100, trace=f"flat-{day}"))
    spans.extend(
        [
            _p95_span(moment, days=0, name="GET /hot", duration=125, trace="hot-now"),
            _p95_span(moment, days=0, name="GET /flat", duration=100, trace="flat-now"),
        ]
    )
    grouped, plain, store = _run_day_pair(
        policy_kwargs=_baseline_policy(
            compare_value_kind=ApmPolicy.CompareValueKind.SIGMA,
            thresholds=[{"severity": "error", "comparator": "gt", "value": "2"}],
        ),
        spans=spans,
        moments=[moment],
    )

    _assert_same_outcome(grouped.id, plain.id, require_recovery=False)
    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped_by_day") == 1


def test_baseline_days_store_calls_do_not_grow_with_target_count():
    moment = _minute()
    counted = []
    for target_count in (3, 30):
        service = _next_service(f"day-calls-{target_count}")
        spans = []
        for index in range(target_count):
            name = f"GET /{index}"
            spans.append(_p95_span(moment, days=0, name=name, duration=400, trace=f"now-{index}"))
            for day in (1, 2, 3):
                spans.append(_p95_span(moment, days=day, name=name, duration=100, trace=f"d{day}-{index}"))
        store = DayRecordingStore(_stamp(service, spans))
        policy = _policy(
            service,
            endpoint_mode=ApmPolicy.EndpointMode.ALL,
            endpoints=[],
            metric_type=ApmPolicy.MetricType.P95,
            compare_mode=ApmPolicy.CompareMode.BASELINE_DAYS,
            compare_offset_amount=3,
            compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
            thresholds=[{"severity": "error", "comparator": "gt", "value": "100"}],
            slow_threshold_ms=None,
            apdex_threshold_ms=None,
        )
        DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)
        counted.append(
            {
                "service_red": store.calls.count("service_red"),
                "service_red_grouped": store.calls.count("service_red_grouped"),
                "service_red_grouped_by_day": store.calls.count("service_red_grouped_by_day"),
                "service_endpoints": store.calls.count("service_endpoints"),
            }
        )

    assert counted[0] == counted[1]
    assert counted[0] == {
        "service_red": 0,
        "service_red_grouped": 1,
        "service_red_grouped_by_day": 1,
        "service_endpoints": 1,
    }


def test_grouped_baseline_days_above_twenty_targets_keeps_the_full_limit():
    moment = _minute()
    names = [f"GET /item-{index}" for index in range(21)]
    service = _next_service("day-full")
    spans = []
    for name in names:
        spans.append(_p95_span(moment, days=0, name=name, duration=100, trace=f"now-{name}"))
        for day in (1, 2):
            spans.append(_p95_span(moment, days=day, name=name, duration=100, trace=f"d{day}-{name}"))
    store = DayRecordingStore(_stamp(service, spans))
    policy = _policy(
        service,
        endpoints=names,
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        metric_type=ApmPolicy.MetricType.P95,
        compare_mode=ApmPolicy.CompareMode.BASELINE_DAYS,
        compare_offset_amount=2,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "100"}],
        slow_threshold_ms=None,
        apdex_threshold_ms=None,
    )
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 21
    assert store.calls.count("service_red_grouped_by_day") == 1
    assert store.calls.count("service_red") == 0


def test_baseline_days_grouped_limit_still_falls_back_per_day_and_caps_at_twenty():
    moment = _minute()
    names = [f"GET /item-{index}" for index in range(21)]

    class FallbackStore:
        def __init__(self):
            self.calls = []

        def service_red(self, query):
            self.calls.append("service_red")
            return ServiceRed(1, 0, 100, 100, request_count=20)

        def service_red_grouped(self, query):
            self.calls.append("service_red_grouped")
            return {(name,): ServiceRed(1, 0, 400, 400, request_count=20) for name in names}

        def service_red_grouped_by_day(self, query, windows):
            self.calls.append("service_red_grouped_by_day")
            raise TelemetryUniqueSpanLimitExceeded("limit")

        def service_red_by_day(self, query, windows):
            self.calls.append("service_red_by_day")
            raise RuntimeError("by day down")

    service = _next_service("day-cap")
    policy = _policy(
        service,
        endpoints=names,
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        metric_type=ApmPolicy.MetricType.P95,
        compare_mode=ApmPolicy.CompareMode.BASELINE_DAYS,
        compare_offset_amount=2,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "1000"}],
        slow_threshold_ms=None,
        apdex_threshold_ms=None,
    )
    store = FallbackStore()
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red_grouped_by_day") == 1
    assert store.calls.count("service_red_by_day") == 1
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 20
    assert ApmPolicyTargetState.objects.filter(policy=policy, last_failed_at__isnull=False).count() == 0


def test_baseline_days_grouped_failure_marks_every_target():
    moment = _minute()
    names = ["GET /a", "GET /b"]

    class DownStore:
        def service_red_grouped(self, query):
            return {(name,): ServiceRed(1, 0, 400, 400, request_count=20) for name in names}

        def service_red_grouped_by_day(self, query, windows):
            raise TelemetryStoreUnavailable("grouped down")

    service = _next_service("day-down")
    policy = _policy(
        service,
        endpoints=names,
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        metric_type=ApmPolicy.MetricType.P95,
        compare_mode=ApmPolicy.CompareMode.BASELINE_DAYS,
        compare_offset_amount=2,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "100"}],
        slow_threshold_ms=None,
        apdex_threshold_ms=None,
    )

    with pytest.raises(TelemetryStoreUnavailable, match="grouped down"):
        DjangoApmPolicyService(DownStore(), InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    states = list(ApmPolicyTargetState.objects.filter(policy=policy))
    assert len(states) == 2
    assert all(state.last_failed_at is not None for state in states)


def _db_span(moment, *, days: int, statement: str, trace: str, duration: float):
    return _live(
        moment - timedelta(days=days),
        trace_id=trace,
        span_id=trace,
        kind="client",
        name="SELECT",
        status="ok",
        duration_ms=duration,
        attributes={"db.system.name": "mysql", "db.statement": statement},
    )


def test_database_baseline_days_group_by_dependency_and_match():
    moment = _minute()
    later = moment + timedelta(minutes=1)
    spans = []
    for anchor, suffix, current in ((moment, "a", 400), (later, "b", 50)):
        spans.append(_db_span(anchor, days=0, statement="SELECT orders", trace=f"orders-{suffix}-0", duration=current))
        spans.append(_db_span(anchor, days=0, statement="SELECT users", trace=f"users-{suffix}-0", duration=100))
        for day, duration in ((1, 100), (2, 200), (3, 300)):
            spans.append(_db_span(anchor, days=day, statement="SELECT orders", trace=f"orders-{suffix}-{day}", duration=duration))
            spans.append(_db_span(anchor, days=day, statement="SELECT users", trace=f"users-{suffix}-{day}", duration=100))
    grouped, plain, store = _run_day_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                {"channel": "database", "system": "mysql", "statement": "SELECT users"},
            ],
            "metric_type": ApmPolicy.MetricType.P95,
            "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
            "compare_offset_amount": 3,
            "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
            "slow_threshold_ms": None,
            "apdex_threshold_ms": None,
        },
        spans=spans,
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red") == 0
    assert store.calls.count("dependency_red_grouped_by_day") == 2


def test_http_baseline_days_stay_per_target():
    moment = _minute()

    def _http(at, trace_id, route, *, status="ok"):
        return _live(
            at,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="GET",
            status=status,
            attributes={"http.request.method": "GET", "http.route": route, "peer.service": "billing"},
        )

    spans = []
    for day, status in ((0, "error"), (1, "ok"), (2, "ok"), (3, "ok")):
        spans.append(_http(moment - timedelta(days=day), f"users-{day}", "/users", status=status))
        spans.append(_http(moment - timedelta(days=day), f"orders-{day}", "/orders"))
    grouped, plain, store = _run_day_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "http", "system": "billing", "statement": "GET /users"},
                {"channel": "http", "system": "billing", "statement": "GET /orders"},
            ],
            "metric_type": ApmPolicy.MetricType.ERROR_RATE,
            "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
            "compare_offset_amount": 3,
            "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.4"}],
        },
        spans=spans,
        moments=[moment],
    )

    _assert_same_outcome(grouped.id, plain.id, require_recovery=False)
    assert store.calls.count("dependency_red_grouped_by_day") == 0
    assert store.calls.count("dependency_red_grouped") == 0
    assert store.calls.count("dependency_red") > 0


def test_overlapping_database_statement_on_baseline_days_falls_back():
    moment = _minute()
    spans = [
        _live(
            moment,
            trace_id="orders-now",
            span_id="orders-now",
            kind="client",
            name="SELECT orders",
            status="error",
            attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
        ),
        _live(
            moment,
            trace_id="plain-now",
            span_id="plain-now",
            kind="client",
            name="SELECT",
            status="ok",
            attributes={"db.system.name": "mysql", "db.statement": "SELECT"},
        ),
    ]
    spans.extend(
        _live(
            moment - timedelta(days=day),
            trace_id=f"span-{day}",
            span_id=f"span-{day}",
            kind="client",
            name="SELECT",
            status="ok",
            attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
        )
        for day in range(1, 4)
    )
    grouped, plain, store = _run_day_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                {"channel": "database", "system": "mysql", "statement": "SELECT"},
            ],
            "metric_type": ApmPolicy.MetricType.ERROR_RATE,
            "compare_mode": ApmPolicy.CompareMode.BASELINE_DAYS,
            "compare_offset_amount": 3,
            "compare_value_kind": ApmPolicy.CompareValueKind.DELTA,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        },
        spans=spans,
        moments=[moment],
    )

    _assert_same_outcome(grouped.id, plain.id, require_recovery=False)
    assert store.calls.count("dependency_red_grouped") == 1
    assert store.calls.count("dependency_red_grouped_by_day") == 1
    assert store.calls.count("dependency_red") > 0
    assert ApmPolicyTargetState.objects.filter(policy=grouped, last_failed_at__isnull=False).count() == 0


def test_previous_window_and_baseline_days_each_group_once():
    moment = _minute()
    service = _next_service("two-kinds")
    spans = _offset_spans(moment, moment + timedelta(minutes=1), timedelta(minutes=1))
    spans.extend(_baseline_day_spans(moment, moment))
    store = DayRecordingStore(_stamp(service, spans))
    policy = _policy(
        service,
        endpoints=["GET /pay", "GET /ok"],
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        metric_type=ApmPolicy.MetricType.ERROR_RATE,
        compare_mode=ApmPolicy.CompareMode.PREVIOUS_WINDOW,
        compare_value_kind=ApmPolicy.CompareValueKind.DELTA,
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.5"}],
        slow_threshold_ms=None,
        apdex_threshold_ms=None,
        conditions=[
            {
                "ref": "a",
                "role": "regular",
                "metric_type": "error_rate",
                "compare_mode": "previous_window",
                "compare_value_kind": "delta",
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
            },
            {
                "ref": "b",
                "role": "regular",
                "metric_type": "error_rate",
                "compare_mode": "baseline_days",
                "compare_offset_amount": 3,
                "compare_value_kind": "delta",
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
            },
        ],
    )
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped") == 2
    assert store.calls.count("service_red_grouped_by_day") == 1
