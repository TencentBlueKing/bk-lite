import inspect
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters.aggregate_red import AggregateApmRedStore, ApmAggregateRedRouter
from apps.apm.adapters.errors import TelemetryQueryTooLarge, TelemetryStoreUnavailable
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery, ServiceMetricQuery, ServiceRed
from apps.apm.tests.helpers import create_application
from apps.core.aggregate_promql import AggregateMetricsTooLarge, AggregateMetricsUnavailable
from apps.core.models.aggregate_origin import AggregateMetricOrigin

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 10, 0, 16, 30, tzinfo=UTC)
ALIGNED = datetime(2026, 11, 10, 0, 15, tzinfo=UTC)
LABELS = 'service_namespace="shop",service_name="checkout",deployment_environment="prod"'
ERROR_LABELS = LABELS + ',status_code="STATUS_CODE_ERROR"'
T1 = 1_794_269_700
T2 = 1_794_269_715


class _Traces:
    def __init__(self):
        self.queries = []

    def service_red(self, query):
        self.queries.append(query)
        return ServiceRed(9, 0, 9, 9)


class _Client:
    def __init__(self, responder=None, *, available=True, error=None):
        self.available = available
        self.responder = responder or (lambda expression, **kwargs: [])
        self.error = error
        self.instant = []
        self.ranges = []

    def query_instant(self, expression, *, at):
        self.instant.append((expression, at))
        if self.error is not None:
            raise self.error
        return self.responder(expression)

    def query_range(self, expression, *, start, end, step_seconds):
        self.ranges.append((expression, start, end, step_seconds))
        if self.error is not None:
            raise self.error
        return self.responder(expression)


def _query(**overrides):
    values = {
        "service_namespace": "shop",
        "service_name": "checkout",
        "environment": "prod",
        "started_at": START,
        "ended_at": END,
        "include_breakdown": True,
    }
    values.update(overrides)
    return ServiceMetricQuery(**values)


def _store(client):
    return AggregateApmRedStore(client, clock=lambda: END)


def _vector(value):
    return [{"metric": {}, "value": [1, value]}]


def _matrix(points):
    return [{"metric": {}, "values": [[timestamp, value] for timestamp, value in points]}]


def _worked_example(expression):
    if "by (shard)" in expression or "shard=" in expression or "apm_aggregate_late" in expression:
        raise AssertionError(expression)
    if expression.startswith("histogram_quantile(0.95") and "by (le, span_name)" in expression:
        return [
            {"metric": {"span_name": "GET /pay", "le": "+Inf"}, "value": [1, "125"]},
            {"metric": {"span_name": "GET /cart", "le": "+Inf"}, "value": [1, "40"]},
        ]
    if expression.startswith("histogram_quantile(0.99") and "by (le, span_name)" in expression:
        return [
            {"metric": {"span_name": "GET /pay", "le": "+Inf"}, "value": [1, "400"]},
            {"metric": {"span_name": "GET /cart", "le": "+Inf"}, "value": [1, "90"]},
        ]
    if expression.startswith("histogram_quantile(0.95"):
        if "[60s]" in expression:
            return _matrix([(T1, "40"), (T2, "80")])
        return _vector("250")
    if expression.startswith("histogram_quantile(0.99"):
        if "[60s]" in expression:
            return _matrix([(T1, "90"), (T2, "110")])
        return _vector("800")
    if "apm_duration_milliseconds_sum" in expression:
        return _vector("90000")
    if "apm_duration_milliseconds_count" in expression:
        return _vector("900")
    if "status_code" in expression and "by (span_name)" in expression:
        return [{"metric": {"span_name": "GET /pay"}, "value": [1, "60"]}]
    if "by (span_name)" in expression:
        return [
            {"metric": {"span_name": "GET /cart"}, "value": [1, "300"]},
            {"metric": {"span_name": "GET /pay"}, "value": [1, "600"]},
        ]
    if "status_code" in expression:
        if "[60s]" in expression:
            return _matrix([(T1, "24")])
        return _vector("90")
    if "apm_calls_total" in expression:
        if "[60s]" in expression:
            return _matrix([(T1, "120"), (T2, "60")])
        return _vector("900")
    raise AssertionError(expression)


def test_aggregate_red_maps_rates_latency_trend_and_top_operations():
    client = _Client(_worked_example)

    red = _store(client).service_red(_query())

    # 900 个请求 / 900 秒，90 个错误，总耗时 90000 毫秒 / 900 次。
    assert red.request_rate == pytest.approx(1.0)
    assert red.error_rate == pytest.approx(0.1)
    assert red.avg_ms == pytest.approx(100)
    assert red.p95_ms == 250
    assert red.p99_ms == 800
    assert red.max_ms is None
    assert red.request_count == 900
    assert red.error_count == 90
    assert red.p50_ms is None
    assert red.slow_count is None
    assert [point.request_rate for point in red.timeseries] == pytest.approx([2.0, 1.0])
    assert red.timeseries[0].error_rate == pytest.approx(0.2)
    assert red.timeseries[1].error_rate == 0
    assert [point.p95_ms for point in red.timeseries] == [40, 80]
    assert all(point.max_ms is None for point in red.timeseries)
    assert red.top_endpoints[0].endpoint == "GET /pay"
    assert red.top_endpoints[0].request_rate == pytest.approx(2 / 3)
    assert red.top_endpoints[0].error_rate == pytest.approx(0.1)
    assert red.top_endpoints[0].p95_ms == 125
    assert red.top_endpoints[0].p99_ms == 400
    assert red.top_endpoints[1].endpoint == "GET /cart"
    assert red.top_endpoints[1].request_rate == pytest.approx(1 / 3)
    assert red.top_endpoints[1].error_rate == 0
    assert red.top_endpoints[1].p95_ms == 40

    expressions = [expression for expression, _ in client.instant]
    assert expressions[0] == f"sum(increase(apm_calls_total{{{LABELS}}}[900s]))"
    assert client.instant[0][1] == ALIGNED
    assert expressions[1] == f"sum(increase(apm_calls_total{{{ERROR_LABELS}}}[900s]))"
    assert expressions[2] == f"sum(increase(apm_duration_milliseconds_sum{{{LABELS}}}[900s]))"
    assert expressions[3] == f"sum(increase(apm_duration_milliseconds_count{{{LABELS}}}[900s]))"
    assert expressions[4] == f"histogram_quantile(0.95, sum by (le) (increase(apm_duration_milliseconds_bucket{{{LABELS}}}[900s])))"
    assert expressions[5] == f"histogram_quantile(0.99, sum by (le) (increase(apm_duration_milliseconds_bucket{{{LABELS}}}[900s])))"
    assert expressions[6] == f"sum by (span_name) (increase(apm_calls_total{{{LABELS}}}[900s]))"
    assert expressions[7] == f"sum by (span_name) (increase(apm_calls_total{{{ERROR_LABELS}}}[900s]))"
    assert expressions[8] == ("histogram_quantile(0.95, sum by (le, span_name) " f"(increase(apm_duration_milliseconds_bucket{{{LABELS}}}[900s])))")
    assert "status_code" not in expressions[2]
    assert "status_code" not in expressions[4]
    assert all("shard" not in expression for expression in expressions)
    assert client.ranges[0][0] == f"sum(increase(apm_calls_total{{{LABELS}}}[60s]))"
    assert client.ranges[0][1:] == (START, ALIGNED, 60)
    assert "STATUS_CODE_ERROR" in client.ranges[1][0]
    assert "[60s]" in client.ranges[2][0]


def test_future_query_end_is_clamped_before_the_flush_interval():
    client = _Client(lambda expression: _vector("900") if "apm_calls_total" in expression and "status_code" not in expression else _vector("0"))

    _store(client).service_red(_query(ended_at=datetime(2026, 11, 10, 0, 30, tzinfo=UTC), include_breakdown=False))

    assert client.instant[0][1] == ALIGNED
    assert "[900s]" in client.instant[0][0]


def test_window_inside_the_flush_interval_is_no_data_without_a_query():
    client = _Client()

    red = _store(client).service_red(
        _query(
            started_at=datetime(2026, 11, 10, 0, 15, 30, tzinfo=UTC),
            ended_at=datetime(2026, 11, 10, 0, 16, 10, tzinfo=UTC),
        )
    )

    assert red.request_rate is None
    assert red.error_rate is None
    assert red.request_count is None
    assert client.instant == []


def test_missing_request_series_is_no_data_and_does_not_query_latency():
    client = _Client(lambda expression: [])

    red = _store(client).service_red(_query())

    assert red == ServiceRed(None, None, None, None)
    assert len(client.instant) == 1
    assert "duration" not in client.instant[0][0]


def test_requests_without_an_error_series_are_zero_errors_not_missing_data():
    def respond(expression):
        if "status_code" in expression or expression.startswith("histogram_quantile"):
            return []
        if "apm_duration_milliseconds_sum" in expression:
            return _vector("90000")
        if "apm_duration_milliseconds_count" in expression:
            return _vector("900")
        return _vector("900")

    red = _store(_Client(respond)).service_red(_query(include_breakdown=False))

    assert red.request_rate == pytest.approx(1.0)
    assert red.error_rate == 0
    assert red.error_count == 0
    assert red.p95_ms is None
    assert red.p99_ms is None
    assert red.avg_ms == pytest.approx(100)
    assert red.max_ms is None


def test_ambiguous_scalar_is_no_data():
    client = _Client(lambda expression: [_vector("900")[0], _vector("1")[0]])

    red = _store(client).service_red(_query())

    assert red.request_rate is None
    assert len(client.instant) == 1


def test_label_values_are_escaped_and_blank_resource_labels_use_unknown():
    client = _Client(lambda expression: [])

    _store(client).service_red(
        _query(
            service_namespace="",
            service_name='a"b\\c',
            environment="",
            endpoint='x"y\nz',
        )
    )

    expression = client.instant[0][0]
    assert 'service_namespace="unknown"' in expression
    assert 'deployment_environment="unknown"' in expression
    assert 'service_name="a\\"b\\\\c"' in expression
    assert 'span_name="x\\"y\\nz"' in expression
    assert "\n" not in expression
    assert 'span_name="x"y' not in expression


def test_aggregate_errors_do_not_fall_back_to_traces():
    traces = _Traces()
    client = _Client(error=AggregateMetricsUnavailable("http"))
    router = ApmAggregateRedRouter(
        traces=traces,
        aggregate=_store(client),
        origin_at=lambda: START,
    )

    with pytest.raises(TelemetryStoreUnavailable, match="^聚合库查询不可用$") as caught:
        router.service_red(_query())

    assert not isinstance(caught.value, TelemetryQueryTooLarge)
    assert traces.queries == []
    assert "http" not in str(caught.value)

    too_large = ApmAggregateRedRouter(
        traces=traces,
        aggregate=_store(_Client(error=AggregateMetricsTooLarge())),
        origin_at=lambda: START,
    )
    with pytest.raises(TelemetryQueryTooLarge, match="^聚合库响应超过大小上限$"):
        too_large.service_red(_query())
    assert traces.queries == []


@pytest.mark.parametrize(
    ("origin", "overrides", "available"),
    [
        (None, {}, True),
        (datetime(2026, 11, 10, 0, 1, tzinfo=UTC), {}, True),
        (START, {"version": "v5"}, True),
        (START, {"instance_id": "pod-a"}, True),
        (START, {"slow_threshold_ms": 800}, True),
        (START, {"apdex_threshold_ms": 500}, True),
        (START, {}, False),
    ],
)
def test_router_reads_traces_outside_the_aggregate_window(origin, overrides, available):
    traces = _Traces()
    client = _Client(available=available)
    router = ApmAggregateRedRouter(traces=traces, aggregate=_store(client), origin_at=lambda: origin)

    red = router.service_red(_query(**overrides))

    assert red.request_rate == 9
    assert client.instant == []
    assert traces.queries[0].service_name == "checkout"


def test_router_reads_aggregate_when_the_window_starts_at_the_recorded_origin():
    traces = _Traces()
    client = _Client(lambda expression: _vector("900"))
    router = ApmAggregateRedRouter(traces=traces, aggregate=_store(client), origin_at=lambda: START)

    red = router.service_red(_query(include_breakdown=False))

    assert red.request_rate == pytest.approx(1.0)
    assert traces.queries == []
    assert client.instant


def test_detail_paths_stay_on_victoria_traces():
    from apps.apm import tasks as apm_tasks
    from apps.apm.views.control_plane import ApmPolicyViewSet, ApmServiceViewSet, ApmSloViewSet
    from apps.apm.views.dashboard import ApmDashboardViewSet

    sources = [
        inspect.getsource(ApmPolicyViewSet._service),
        inspect.getsource(ApmServiceViewSet.error_breakdown),
        inspect.getsource(ApmServiceViewSet.client_rollups),
        inspect.getsource(apm_tasks.evaluate_apm_policy),
    ]
    for source in sources:
        assert "apm_entry_red_store" not in source
        assert "apm_availability_slo_store" not in source
        assert "VictoriaTracesTelemetryStore" in source
    assert "apm_entry_red_store" not in inspect.getsource(ApmPolicyViewSet.dry_run)
    slo_source = inspect.getsource(ApmSloViewSet._service)
    dashboard_source = inspect.getsource(ApmDashboardViewSet.list)
    assert "apm_availability_slo_store" in slo_source
    assert "apm_availability_slo_store" in dashboard_source


def _discover(application_id, namespace, name, instance, organization):
    create_application(application_id, (organization,))
    return DjangoTelemetryCatalogService().discover(CatalogDiscovery(namespace, name, instance, "production")).service


def _window_params():
    ended = timezone.now().replace(microsecond=0)
    started = ended - timedelta(minutes=16)
    return {"started_at": started.isoformat(), "ended_at": ended.isoformat()}


def _install_reader(monkeypatch, client):
    monkeypatch.setattr("apps.apm.adapters.aggregate_red.AggregatePromqlClient.from_env", lambda: client)
    monkeypatch.setattr(
        "apps.apm.adapters.victoriatraces.VictoriaTracesTelemetryStore.service_red",
        lambda self, query: (_ for _ in ()).throw(AssertionError("traces")),
    )


def _install_inline_batch(monkeypatch):
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

    monkeypatch.setattr("apps.apm.views.control_plane.ThreadPoolExecutor", _Pool)
    monkeypatch.setattr("apps.apm.views.control_plane.as_completed", lambda futures: list(futures))


def test_service_red_api_narrows_promql_to_the_authorized_service(apm_api_client, monkeypatch):
    own = _discover("shop", "shop", "checkout", "pod-a", 10)
    hidden = _discover("billing", "billing", "secret", "pod-b", 20)
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    client = _Client(lambda expression: [])
    _install_reader(monkeypatch, client)
    endpoint = 'pay"} or up{job="x'

    response = apm_api_client.get(
        f"/api/v1/apm/services/{own.id}/metrics/",
        {"environment": "production", "include_breakdown": "false", "endpoint": endpoint, **_window_params()},
    )
    hidden_response = apm_api_client.get(
        f"/api/v1/apm/services/{hidden.id}/metrics/",
        {"environment": "production", **_window_params()},
    )

    assert response.status_code == 200
    assert response.data["data_state"] == "no_data"
    assert response.data["request_rate"] is None
    assert response.data["max_ms"] is None
    assert hidden_response.status_code == 404
    assert len(client.instant) == 1
    expression = client.instant[0][0]
    assert 'service_namespace="shop"' in expression
    assert 'service_name="checkout"' in expression
    assert 'deployment_environment="production"' in expression
    assert 'span_name="pay\\"} or up{job=\\"x"' in expression
    assert "billing" not in expression
    assert "secret" not in expression
    assert "shard" not in expression


def test_service_red_batch_skips_services_outside_the_tenant(apm_api_client, monkeypatch):
    own = _discover("shop", "shop", "checkout", "pod-a", 10)
    hidden = _discover("billing", "billing", "secret", "pod-b", 20)
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    client = _Client(lambda expression: [])
    _install_reader(monkeypatch, client)
    _install_inline_batch(monkeypatch)

    response = apm_api_client.post(
        "/api/v1/apm/services/metrics/batch/",
        {
            **_window_params(),
            "include_breakdown": False,
            "targets": [
                {"service_id": str(own.id), "environment": "production"},
                {"service_id": str(hidden.id), "environment": "production"},
            ],
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["items"][0]["ok"] is True
    assert response.data["items"][0]["data_state"] == "no_data"
    assert response.data["items"][1]["ok"] is False
    assert response.data["items"][1]["code"] == "not_found"
    assert len(client.instant) == 1
    expression = client.instant[0][0]
    assert 'service_name="checkout"' in expression
    assert "secret" not in expression
    assert "billing" not in expression


def test_service_red_api_degrades_when_the_aggregate_store_fails(apm_api_client, monkeypatch):
    own = _discover("shop", "shop", "checkout", "pod-a", 10)
    AggregateMetricOrigin.objects.create(product="apm", started_at=datetime(2026, 1, 1, tzinfo=UTC))
    client = _Client(error=AggregateMetricsUnavailable("http"))
    _install_reader(monkeypatch, client)

    unavailable = apm_api_client.get(
        f"/api/v1/apm/services/{own.id}/metrics/",
        {"environment": "production", "include_breakdown": "false", **_window_params()},
    )
    client.error = AggregateMetricsTooLarge()
    too_large = apm_api_client.get(
        f"/api/v1/apm/services/{own.id}/metrics/",
        {"environment": "production", "include_breakdown": "false", **_window_params()},
    )

    assert unavailable.status_code == 503
    assert unavailable.data["code"] == "telemetry_unavailable"
    assert unavailable.data["detail"] == "聚合库查询不可用"
    assert too_large.status_code == 503
    assert too_large.data["code"] == "query_too_large"
    assert too_large.data["detail"] == "聚合库响应超过大小上限"


def test_service_red_api_uses_traces_when_no_origin_is_recorded(apm_api_client, monkeypatch):
    own = _discover("shop", "shop", "checkout", "pod-a", 10)
    client = _Client()
    monkeypatch.setattr("apps.apm.adapters.aggregate_red.AggregatePromqlClient.from_env", lambda: client)
    monkeypatch.setattr(
        "apps.apm.adapters.victoriatraces.VictoriaTracesTelemetryStore.service_red",
        lambda self, query: ServiceRed(4, 0, 4, 4),
    )

    response = apm_api_client.get(
        f"/api/v1/apm/services/{own.id}/metrics/",
        {"environment": "production", **_window_params()},
    )

    assert response.status_code == 200
    assert response.data["request_rate"] == 4
    assert client.instant == []


def test_openapi_service_metrics_reader_uses_the_aggregate_router(monkeypatch):
    monkeypatch.delenv("AGG_VICTORIAMETRICS_QUERY_URL", raising=False)
    monkeypatch.setenv("VICTORIAMETRICS_HOST", "http://monitor.example:8428")
    from apps.apm.adapters.aggregate_red import apm_entry_red_store
    from apps.apm.openapi_service import _service_metrics_reader

    reader = _service_metrics_reader()

    assert type(reader.metric_store) is type(apm_entry_red_store())
    assert reader.metric_store.aggregate.available is False
