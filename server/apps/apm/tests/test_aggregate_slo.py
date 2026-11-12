from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from apps.apm.adapters.aggregate_red import AggregateApmRedStore, ApmAvailabilitySloStore
from apps.apm.adapters.errors import TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.models import ApmSlo
from apps.apm.services.contracts import MetricDataState, SloMeasurement, SloMetricQuery
from apps.apm.services.reliability import DjangoApmReliabilityService
from apps.core.aggregate_promql import AggregateMetricsTooLarge, AggregateMetricsUnavailable
from apps.core.models.aggregate_origin import AggregateMetricOrigin

# 2026-11-10 12:00:30 对齐到完整分钟后再留 60 秒刷出，结束于 11:59:00，比原结束早 90 秒。
EVALUATED = datetime(2026, 11, 10, 12, 0, 30, tzinfo=UTC)
ALIGNED = datetime(2026, 11, 10, 11, 59, tzinfo=UTC)
START_7D = datetime(2026, 11, 3, 12, 0, 30, tzinfo=UTC)
START_30D = datetime(2026, 10, 11, 12, 0, 30, tzinfo=UTC)
START_MONTH = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
WINDOW_7D = 604_710
WINDOW_30D = 2_591_910
WINDOW_MONTH = 820_740
LABELS = 'service_namespace="shop",service_name="checkout",deployment_environment="prod"'


class _Traces:
    def __init__(self, measurement=None):
        self.queries = []
        self.measurement = measurement

    def slo_measurement(self, query):
        self.queries.append(query)
        if self.measurement is None:
            raise AssertionError("traces")
        return self.measurement


class _Client:
    def __init__(self, responder=None, *, available=True):
        self.available = available
        self.responder = responder or (lambda expression: [])
        self.instant = []

    def query_instant(self, expression, *, at):
        self.instant.append((expression, at))
        return self.responder(expression)

    def query_range(self, expression, *, start, end, step_seconds):
        return []


def _vector(value):
    return [{"metric": {}, "value": [1, value]}]


def _query(**overrides):
    values = {
        "service_namespace": "shop",
        "service_name": "checkout",
        "environment": "prod",
        "started_at": START_7D,
        "ended_at": EVALUATED,
        "sli_type": "availability",
    }
    values.update(overrides)
    return SloMetricQuery(**values)


def _store(client, traces=None, *, origin=START_7D):
    return ApmAvailabilitySloStore(
        traces=traces or _Traces(),
        aggregate=AggregateApmRedStore(client, clock=lambda: EVALUATED),
        origin_at=lambda: origin,
    )


def _rule(**overrides):
    values = {
        "is_enabled": True,
        "service": SimpleNamespace(namespace="shop", name="checkout"),
        "environment": "prod",
        "endpoint": "",
        "sli_type": "availability",
        "latency_threshold_ms": None,
        "objective": 99.9,
        "evaluation_window": "rolling7d",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _counts(expression):
    if "status_code" in expression:
        return _vector("25")
    if "apm_calls_total" in expression:
        return _vector("1000")
    return _vector("1")


def test_availability_sli_uses_increase_over_the_aligned_seven_day_window():
    client = _Client(lambda expression: _vector("25") if "status_code" in expression else _vector("1000"))
    store = ApmAvailabilitySloStore(
        traces=_Traces(),
        aggregate=AggregateApmRedStore(client, clock=lambda: EVALUATED),
        origin_at=lambda: START_7D,
    )

    measurement = store.slo_measurement(_query())

    # 1000 次调用里 25 次错误，好事件 975。
    assert measurement.data_state == MetricDataState.AVAILABLE
    assert measurement.compliance_percent == pytest.approx(97.5)
    assert measurement.total_rate == pytest.approx(1000 / WINDOW_7D)
    assert measurement.good_rate == pytest.approx(975 / WINDOW_7D)
    assert client.instant[0] == (
        f"sum(increase(apm_calls_total{{{LABELS}}}[{WINDOW_7D}s]))",
        ALIGNED,
    )
    assert client.instant[1][0] == (f'sum(increase(apm_calls_total{{{LABELS},status_code="STATUS_CODE_ERROR"}}[{WINDOW_7D}s]))')
    assert "shard" not in client.instant[0][0]
    assert "shard" not in client.instant[1][0]


TRACES_RESULT = SloMeasurement(88.0, 1.0, 2.0, MetricDataState.AVAILABLE)


@pytest.mark.parametrize(
    ("window", "origin", "seconds"),
    [
        ("rolling30d", START_30D, WINDOW_30D),
        ("calendarMonth", START_MONTH, WINDOW_MONTH),
    ],
)
def test_thirty_day_and_calendar_month_windows_use_increase_seconds(window, origin, seconds):
    client = _Client(_counts)
    result = DjangoApmReliabilityService(_store(client, origin=origin)).evaluate(
        _rule(evaluation_window=window),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate == pytest.approx(97.5)
    assert result.data_state == "available"
    assert client.instant[0] == (
        f"sum(increase(apm_calls_total{{{LABELS}}}[{seconds}s]))",
        ALIGNED,
    )
    assert 'status_code="STATUS_CODE_ERROR"' in client.instant[1][0]
    assert client.instant[1][0].endswith(f"[{seconds}s]))")


@pytest.mark.parametrize(
    ("origin", "available"),
    [
        (START_7D + timedelta(seconds=1), True),
        (None, True),
        (START_7D, False),
    ],
)
def test_availability_uses_traces_when_the_aggregate_window_is_not_covered(origin, available):
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts, available=available)

    measurement = _store(client, traces, origin=origin).slo_measurement(_query())

    assert measurement.compliance_percent == 88.0
    assert client.instant == []
    assert traces.queries[0].started_at == START_7D
    assert traces.queries[0].ended_at == EVALUATED


@pytest.mark.parametrize("sli_type", ["latency_p95", "latency_p99"])
def test_latency_slo_keeps_the_original_victoria_traces_query(sli_type):
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    measurement = _store(client, traces).slo_measurement(_query(sli_type=sli_type, latency_threshold_ms=300))

    assert measurement.compliance_percent == 88.0
    assert client.instant == []
    assert traces.queries[0].sli_type == sli_type
    assert traces.queries[0].latency_threshold_ms == 300
    assert traces.queries[0].started_at == START_7D
    assert traces.queries[0].ended_at == EVALUATED


def test_trace_fallback_omits_compliance_when_retention_is_shorter_than_the_window(monkeypatch):
    monkeypatch.setenv("APM_TRACE_RETENTION", "7d")
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)
    store = _store(client, traces, origin=None)

    with pytest.raises(TelemetryStoreUnavailable, match="^明细保留期不足$"):
        store.slo_measurement(_query(started_at=START_30D))
    result = DjangoApmReliabilityService(store).evaluate(
        _rule(evaluation_window="rolling30d"),
        evaluated_at=EVALUATED,
    )

    assert traces.queries == []
    assert client.instant == []
    assert result.current_rate is None
    assert result.budget_remaining is None
    assert result.data_state == "no_data"
    assert result.reason == "明细保留期不足"


@pytest.mark.parametrize("retention", ["7d", "168h"])
def test_trace_fallback_calculates_when_retention_equals_the_window(monkeypatch, retention):
    monkeypatch.setenv("APM_TRACE_RETENTION", retention)
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=None)).evaluate(
        _rule(evaluation_window="rolling7d"),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate == 88.0
    assert result.budget_remaining == 0.0
    assert result.data_state == "available"
    assert result.reason == ""
    assert len(traces.queries) == 1
    assert client.instant == []


@pytest.mark.parametrize(
    ("retention", "expected_rate"),
    [
        ("9d", None),
        ("10d", 88.0),
    ],
)
def test_calendar_month_compares_trace_retention_with_the_actual_span(monkeypatch, retention, expected_rate):
    # 2026-11-01 00:00 到 2026-11-10 12:00:30，实际跨度 9 天 12.5 小时，不是固定 30 天。
    monkeypatch.setenv("APM_TRACE_RETENTION", retention)
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=None)).evaluate(
        _rule(evaluation_window="calendarMonth"),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate == expected_rate
    assert client.instant == []
    if expected_rate is None:
        assert result.reason == "明细保留期不足"
        assert result.budget_remaining is None
        assert traces.queries == []
    else:
        assert result.data_state == "available"
        assert traces.queries[0].started_at == START_MONTH


def test_aggregate_path_ignores_trace_retention(monkeypatch):
    monkeypatch.setenv("APM_TRACE_RETENTION", "7d")
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=START_30D)).evaluate(
        _rule(evaluation_window="rolling30d"),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate == pytest.approx(97.5)
    assert result.data_state == "available"
    assert traces.queries == []
    assert client.instant[0][0].startswith("sum(increase(apm_calls_total{")


def test_latency_slo_omits_compliance_when_trace_retention_is_shorter_than_the_window(monkeypatch):
    monkeypatch.setenv("APM_TRACE_RETENTION", "7d")
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=START_30D)).evaluate(
        _rule(evaluation_window="rolling30d", sli_type="latency_p99", latency_threshold_ms=300),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate is None
    assert result.budget_remaining is None
    assert result.data_state == "no_data"
    assert result.reason == "明细保留期不足"
    assert traces.queries == []
    assert client.instant == []


def test_unparseable_trace_retention_omits_compliance_without_querying(monkeypatch):
    monkeypatch.setenv("APM_TRACE_RETENTION", "35days")
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=None)).evaluate(
        _rule(evaluation_window="rolling7d"),
        evaluated_at=EVALUATED,
    )

    assert traces.queries == []
    assert client.instant == []
    assert result.current_rate is None
    assert result.budget_remaining is None
    assert result.data_state == "no_data"
    assert result.reason == "明细保留期配置无效"


def test_aggregate_path_ignores_unparseable_trace_retention(monkeypatch):
    monkeypatch.setenv("APM_TRACE_RETENTION", "35days")
    traces = _Traces(TRACES_RESULT)
    client = _Client(_counts)

    result = DjangoApmReliabilityService(_store(client, traces, origin=START_7D)).evaluate(
        _rule(evaluation_window="rolling7d"),
        evaluated_at=EVALUATED,
    )

    assert result.current_rate == pytest.approx(97.5)
    assert result.data_state == "available"
    assert traces.queries == []


@pytest.mark.parametrize(
    ("error", "exc_type", "message"),
    [
        (AggregateMetricsUnavailable("http"), TelemetryStoreUnavailable, "聚合库查询不可用"),
        (AggregateMetricsTooLarge(), TelemetryQueryTooLarge, "聚合库响应超过大小上限"),
    ],
)
def test_aggregate_errors_degrade_without_scanning_traces_or_returning_zero(error, exc_type, message):
    traces = _Traces(SloMeasurement(0.0, 0.0, 1.0, MetricDataState.AVAILABLE))
    client = _Client(lambda expression: (_ for _ in ()).throw(error))
    store = _store(client, traces)

    with pytest.raises(exc_type, match=f"^{message}$"):
        store.slo_measurement(_query())
    result = DjangoApmReliabilityService(store).evaluate(_rule(), evaluated_at=EVALUATED)

    assert traces.queries == []
    assert result.current_rate is None
    assert result.budget_remaining is None
    assert result.data_state == "no_data"
    assert result.reason == message


def test_missing_or_zero_samples_stay_no_data():
    traces = _Traces(SloMeasurement(0.0, 0.0, 1.0, MetricDataState.AVAILABLE))
    empty = _Client(lambda expression: [])
    zero = _Client(lambda expression: _vector("0"))

    missing = _store(empty, traces).slo_measurement(_query())
    nothing = _store(zero, traces).slo_measurement(_query())

    assert missing.compliance_percent is None
    assert missing.data_state == MetricDataState.NO_DATA
    assert nothing.compliance_percent is None
    assert len(zero.instant) == 1
    assert traces.queries == []
    evaluated = DjangoApmReliabilityService(_store(empty, traces)).evaluate(_rule(), evaluated_at=EVALUATED)
    assert evaluated.current_rate is None
    assert evaluated.reason == "no_samples"


def test_absent_error_series_counts_as_zero_bad_events():
    client = _Client(lambda expression: [] if "status_code" in expression else _vector("1000"))

    measurement = _store(client).slo_measurement(_query())

    assert measurement.compliance_percent == pytest.approx(100)
    assert measurement.good_rate == pytest.approx(1000 / WINDOW_7D)


def test_selector_narrows_to_the_slo_scope_and_escapes_label_values():
    client = _Client(_counts)
    endpoint = 'pay"} or up{job="x'

    _store(client).slo_measurement(
        _query(service_namespace='shop" or', environment="prod", endpoint=endpoint),
    )

    expression = client.instant[0][0]
    assert 'service_namespace="shop\\" or"' in expression
    assert 'service_name="checkout"' in expression
    assert 'deployment_environment="prod"' in expression
    assert 'span_name="pay\\"} or up{job=\\"x"' in expression
    assert "shard" not in expression


def test_flush_gap_inside_a_covered_window_does_not_scan_traces():
    traces = _Traces(SloMeasurement(0.0, 0.0, 1.0, MetricDataState.AVAILABLE))
    client = _Client(_counts)
    started = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    measurement = _store(client, traces, origin=started).slo_measurement(_query(started_at=started))

    assert measurement.compliance_percent is None
    assert measurement.data_state == MetricDataState.NO_DATA
    assert client.instant == []
    assert traces.queries == []


def _run_dashboard_inline(monkeypatch):
    class _Done:
        def __init__(self, fn, args, kwargs):
            self._fn = fn
            self._args = args
            self._kwargs = kwargs

        def result(self):
            return self._fn(*self._args, **self._kwargs)

    class _Pool:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            return _Done(fn, args, kwargs)

    monkeypatch.setattr("apps.apm.services.dashboard.ThreadPoolExecutor", _Pool)
    monkeypatch.setattr("apps.apm.services.dashboard.as_completed", lambda futures: list(futures))


def _visible_service():
    from django.utils import timezone

    from apps.apm.models import ApmService, ApmServiceInstance, ApmServiceOrganization

    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    ApmServiceInstance.objects.create(
        service=service,
        instance_id="checkout-1",
        normalized_instance_id="checkout-1",
        environment="production",
        first_seen_at=now,
        last_seen_at=now,
    )
    return service


@pytest.mark.django_db
def test_dashboard_list_and_detail_share_the_aggregate_availability_rate(apm_api_client, monkeypatch):
    service = _visible_service()
    slo = ApmSlo.objects.create(
        name="结算可用性",
        service=service,
        environment="production",
        endpoint='pay"} or up{job="x',
        sli_type="availability",
        objective="99.900",
        evaluation_window="rolling7d",
    )
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    _run_dashboard_inline(monkeypatch)
    monkeypatch.setattr("apps.apm.adapters.aggregate_red.AggregatePromqlClient.from_env", lambda: _Client(_counts))
    monkeypatch.setattr(
        "apps.apm.adapters.victoriatraces.VictoriaTracesTelemetryStore.slo_measurement",
        lambda self, query: (_ for _ in ()).throw(AssertionError("traces")),
    )

    dashboard = apm_api_client.get("/api/v1/apm/dashboard/?window=1h")
    listed = apm_api_client.get("/api/v1/apm/slos/")
    detail = apm_api_client.get(f"/api/v1/apm/slos/{slo.id}/")

    assert dashboard.status_code == 200
    card = dashboard.data["slos"]["data"]["items"][0]
    assert card["current_rate"] == pytest.approx(97.5)
    assert listed.status_code == 200
    assert listed.data[0]["current_rate"] == pytest.approx(card["current_rate"])
    assert detail.status_code == 200
    assert detail.data["current_rate"] == pytest.approx(card["current_rate"])
    assert listed.data[0]["id"] == detail.data["id"] == str(slo.id)


@pytest.mark.django_db
def test_slo_pages_degrade_when_the_aggregate_store_fails(apm_api_client, monkeypatch):
    service = _visible_service()
    ApmSlo.objects.create(
        name="结算可用性",
        service=service,
        environment="production",
        sli_type="availability",
        objective="99.900",
        evaluation_window="rolling30d",
    )
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    _run_dashboard_inline(monkeypatch)
    monkeypatch.setattr(
        "apps.apm.adapters.aggregate_red.AggregatePromqlClient.from_env",
        lambda: _Client(lambda expression: (_ for _ in ()).throw(AggregateMetricsUnavailable("http"))),
    )
    scanned = []
    monkeypatch.setattr(
        "apps.apm.adapters.victoriatraces.VictoriaTracesTelemetryStore.slo_measurement",
        lambda self, query: scanned.append(query) or SloMeasurement(0.0, 0.0, 1.0, MetricDataState.AVAILABLE),
    )

    dashboard = apm_api_client.get("/api/v1/apm/dashboard/?window=1h")
    listed = apm_api_client.get("/api/v1/apm/slos/")

    assert scanned == []
    assert listed.status_code == 200
    assert listed.data[0]["current_rate"] is None
    assert listed.data[0]["data_state"] == "no_data"
    assert listed.data[0]["reason"] == "聚合库查询不可用"
    assert dashboard.status_code == 200
    assert dashboard.data["slos"]["status"] == "failed"
    assert dashboard.data["slos"]["error"] == "聚合库查询不可用"


@pytest.mark.django_db
def test_dashboard_list_and_detail_share_empty_rate_when_trace_retention_is_short(apm_api_client, monkeypatch):
    service = _visible_service()
    slo = ApmSlo.objects.create(
        name="结算时延",
        service=service,
        environment="production",
        sli_type="latency_p95",
        objective="95.000",
        latency_threshold_ms=300,
        evaluation_window="rolling30d",
    )
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setenv("APM_TRACE_RETENTION", "7d")
    _run_dashboard_inline(monkeypatch)
    monkeypatch.setattr("apps.apm.adapters.aggregate_red.AggregatePromqlClient.from_env", lambda: _Client(_counts))
    scanned = []
    monkeypatch.setattr(
        "apps.apm.adapters.victoriatraces.VictoriaTracesTelemetryStore.slo_measurement",
        lambda self, query: scanned.append(query) or SloMeasurement(50.0, 1.0, 2.0, MetricDataState.AVAILABLE),
    )

    dashboard = apm_api_client.get("/api/v1/apm/dashboard/?window=1h")
    listed = apm_api_client.get("/api/v1/apm/slos/")
    detail = apm_api_client.get(f"/api/v1/apm/slos/{slo.id}/")

    assert scanned == []
    assert listed.status_code == 200
    assert listed.data[0]["current_rate"] is None
    assert listed.data[0]["budget_remaining"] is None
    assert listed.data[0]["data_state"] == "no_data"
    assert listed.data[0]["reason"] == "明细保留期不足"
    assert detail.status_code == 200
    assert detail.data["current_rate"] is None
    assert detail.data["reason"] == listed.data[0]["reason"]
    assert detail.data["id"] == listed.data[0]["id"] == str(slo.id)
    assert dashboard.status_code == 200
    assert dashboard.data["slos"]["status"] == "ok"
    card = dashboard.data["slos"]["data"]["items"][0]
    assert card["current_rate"] is None
    assert card["met"] is None
    assert card["reason"] == listed.data[0]["reason"]
    assert card["id"] == str(slo.id)
