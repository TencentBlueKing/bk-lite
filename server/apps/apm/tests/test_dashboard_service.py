from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models.query import QuerySet
from django.utils import timezone

from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmAlert, ApmDeploymentEvent, ApmService, ApmServiceInstance, ApmServiceOrganization, ApmSlo
from apps.apm.services.contracts import GroupedRed, GroupedRedOverview, ServiceRed, ServiceRedPoint, SloEvaluation, SloMeasurement
from apps.apm.services.dashboard import SPARKLINE_POINTS, ApmDashboardService
from apps.apm.services.reliability import DjangoApmReliabilityService

pytestmark = pytest.mark.django_db


class StubMetricStore:
    def __init__(self, red_by_name: dict[str, ServiceRed], slo_rate: float | None = 99.9):
        self.red_by_name = red_by_name
        self.slo_rate = slo_rate
        self.fail_names: set[str] = set()
        self.deployment_release_calls = 0
        self.service_red_calls: list[tuple[str, str]] = []

    def service_red(self, query):
        self.service_red_calls.append((query.service_name, query.environment))
        if query.service_name in self.fail_names:
            raise RuntimeError("vt down")
        return self.red_by_name[query.service_name]

    def slo_measurement(self, query):
        if self.slo_rate is None:
            return SloMeasurement(None, None, None, "no_data")
        return SloMeasurement(self.slo_rate, 1.0, 1.0, "available")

    def deployment_releases(self, query):
        self.deployment_release_calls += 1
        return []


def _service(*, organization=10, namespace="shop", name="checkout", last_seen_at=None):
    now = last_seen_at or timezone.now()
    service = ApmService.objects.create(
        namespace=namespace,
        normalized_namespace=namespace,
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    ApmServiceInstance.objects.create(
        service=service,
        instance_id=f"{name}-1",
        normalized_instance_id=f"{name}-1",
        environment="production",
        first_seen_at=now,
        last_seen_at=now,
    )
    return service


def _red(*, request_rate=10.0, error_rate=0.02, p95_ms=200.0, points=4):
    now = timezone.now()
    timeseries = tuple(
        ServiceRedPoint(
            timestamp=now - timedelta(minutes=points - index),
            request_rate=request_rate,
            error_rate=error_rate,
            p95_ms=p95_ms,
            p99_ms=p95_ms + 20,
        )
        for index in range(points)
    )
    return ServiceRed(request_rate, error_rate, p95_ms, p95_ms + 20, timeseries=timeseries)


def test_dashboard_empty_when_organization_has_no_services():
    payload = ApmDashboardService(metric_store=StubMetricStore({})).build(organization_id=10, window="1h")

    assert payload["empty"] is True
    assert payload["aggregate_notice"] is None
    assert payload["kpis"]["status"] == "empty"
    assert payload["health"]["status"] == "empty"
    assert payload["top_error_rate"]["status"] == "empty"
    assert payload["top_p95"]["status"] == "empty"
    assert payload["releases"]["status"] == "empty"


def test_dashboard_aggregates_kpis_health_alerts_and_releases():
    now = timezone.now()
    checkout = _service(name="checkout", last_seen_at=now)
    payment = _service(name="payment", last_seen_at=now)
    _service(organization=20, name="hidden", last_seen_at=now)

    ApmAlert.objects.create(
        external_id="alert-1",
        policy_id_snapshot="p1",
        policy_name="错误率过高",
        service=checkout,
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        metric_type="error_rate",
        severity="critical",
        status=ApmAlert.Status.ACTIVE,
        organizations=[10],
        started_at=now - timedelta(minutes=5),
        last_event_at=now - timedelta(minutes=5),
    )
    ApmAlert.objects.create(
        external_id="alert-hidden",
        policy_id_snapshot="p2",
        policy_name="隐藏告警",
        service_namespace="shop",
        service_name="hidden",
        environment="production",
        metric_type="error_rate",
        severity="warning",
        status=ApmAlert.Status.ACTIVE,
        organizations=[20],
        started_at=now - timedelta(minutes=1),
        last_event_at=now - timedelta(minutes=1),
    )

    store = StubMetricStore(
        {
            "checkout": _red(request_rate=10.0, error_rate=0.08, p95_ms=400.0),
            "payment": _red(request_rate=5.0, error_rate=0.001, p95_ms=120.0),
        }
    )
    payload = ApmDashboardService(metric_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert payload["empty"] is False
    assert payload["aggregate_notice"] is None
    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["application_count"] == 1
    assert payload["kpis"]["data"]["service_count"] == 2
    assert payload["kpis"]["data"]["active_alert_count"] == 1
    assert payload["kpis"]["data"]["request_rate"] == pytest.approx(15.0)
    assert payload["kpis"]["data"]["error_request_rate"] == pytest.approx(10.0 * 0.08 + 5.0 * 0.001)
    assert payload["health"]["status"] == "ok"
    buckets = {item["key"]: item["count"] for item in payload["health"]["data"]["buckets"]}
    assert buckets["critical"] == 1
    assert buckets["healthy"] == 1
    assert payload["alerts"]["status"] == "ok"
    assert payload["alerts"]["data"]["items"][0]["service"] == "checkout"
    assert payload["alerts"]["data"]["items"][0]["severity"] == "critical"
    assert payload["top_error_rate"]["data"]["items"][0]["service_name"] == "checkout"
    assert payload["top_p95"]["data"]["items"][0]["service_name"] == "checkout"
    assert payload["releases"]["status"] == "empty"
    assert payment.name == "payment"


def test_dashboard_releases_reads_materialized_events():
    now = timezone.now()
    checkout = _service(name="checkout", last_seen_at=now)
    _service(name="payment", last_seen_at=now)
    hidden = _service(organization=20, name="hidden", last_seen_at=now)
    visible = ApmDeploymentEvent.objects.create(
        service=checkout,
        environment="production",
        version="v5.3.0",
        deployed_at=now - timedelta(hours=2),
        status=ApmDeploymentEvent.Status.SUCCESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )
    ApmDeploymentEvent.objects.create(
        service=checkout,
        environment="production",
        version="v5.2.9",
        deployed_at=now - timedelta(days=8),
        status=ApmDeploymentEvent.Status.SUCCESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )
    ApmDeploymentEvent.objects.create(
        service=hidden,
        environment="production",
        version="v9.9.9",
        deployed_at=now - timedelta(hours=1),
        status=ApmDeploymentEvent.Status.SUCCESS,
        source=ApmDeploymentEvent.Source.INFERRED,
    )
    store = StubMetricStore({"checkout": _red(), "payment": _red()})
    payload = ApmDashboardService(metric_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert payload["releases"]["status"] == "ok"
    items = payload["releases"]["data"]["items"]
    assert [item["id"] for item in items] == [str(visible.id)]
    assert items[0]["service_name"] == "checkout"
    assert items[0]["version"] == "v5.3.0"
    assert items[0]["status"] == "success"
    assert items[0]["source"] == "inferred"
    assert store.deployment_release_calls == 0


def test_dashboard_section_failure_does_not_break_other_sections(mocker):
    now = timezone.now()
    _service(name="checkout", last_seen_at=now)
    store = StubMetricStore({"checkout": _red()})
    service = ApmDashboardService(metric_store=store, now_fn=lambda: now)
    mocker.patch.object(service, "_build_alerts", side_effect=RuntimeError("alerts down"))

    payload = service.build(organization_id=10, window="1h")

    assert payload["empty"] is False
    assert payload["kpis"]["status"] == "ok"
    assert payload["alerts"]["status"] == "failed"
    assert "alerts down" in payload["alerts"]["error"]
    assert payload["releases"]["status"] == "empty"


def test_dashboard_slo_overview_marks_met_against_objective(mocker):
    now = timezone.now()
    service = _service(name="checkout", last_seen_at=now)
    ApmSlo.objects.create(
        name="可用性",
        service=service,
        environment="production",
        sli_type="availability",
        objective=Decimal("99.900"),
        evaluation_window="rolling7d",
        is_enabled=True,
    )
    reliability = mocker.Mock(spec=DjangoApmReliabilityService)
    reliability.evaluate.return_value = SloEvaluation(
        current_rate=98.5,
        budget_remaining=10.0,
        data_state="available",
        started_at=now - timedelta(days=7),
        ended_at=now,
    )
    store = StubMetricStore({"checkout": _red()})
    payload = ApmDashboardService(
        metric_store=store,
        reliability=reliability,
        now_fn=lambda: now,
    ).build(organization_id=10, window="1h")

    assert payload["slos"]["status"] == "ok"
    row = payload["slos"]["data"]["items"][0]
    assert row["service_name"] == "checkout"
    assert row["met"] is False
    assert row["current_rate"] == 98.5


def test_dashboard_slo_overview_skips_unavailable_evaluations(mocker):
    now = timezone.now()
    service = _service(name="checkout", last_seen_at=now)
    ApmSlo.objects.create(
        name="全量可用性",
        service=service,
        environment="production",
        sli_type="availability",
        objective=Decimal("99.900"),
        evaluation_window="rolling7d",
        is_enabled=True,
    )
    ApmSlo.objects.create(
        name="结算时延",
        service=service,
        environment="production",
        endpoint="POST /api/checkout",
        sli_type="latency_p95",
        objective=Decimal("95.000"),
        latency_threshold_ms=500,
        evaluation_window="rolling7d",
        is_enabled=True,
    )
    reliability = mocker.Mock(spec=DjangoApmReliabilityService)

    def _evaluate(slo, *, evaluated_at):
        if slo.name == "全量可用性":
            return SloEvaluation(
                current_rate=None,
                budget_remaining=None,
                data_state="no_data",
                started_at=now - timedelta(days=7),
                ended_at=now,
                reason="VictoriaTraces 查询不可用",
            )
        return SloEvaluation(
            current_rate=96.0,
            budget_remaining=20.0,
            data_state="available",
            started_at=now - timedelta(days=7),
            ended_at=now,
        )

    reliability.evaluate.side_effect = _evaluate
    store = StubMetricStore({"checkout": _red()})
    payload = ApmDashboardService(
        metric_store=store,
        reliability=reliability,
        now_fn=lambda: now,
    ).build(organization_id=10, window="1h")

    assert payload["slos"]["status"] == "ok"
    assert len(payload["slos"]["data"]["items"]) == 1
    assert payload["slos"]["data"]["items"][0]["service_name"] == "checkout"


def test_dashboard_slo_section_fails_when_every_evaluation_has_no_rate(mocker):
    now = timezone.now()
    service = _service(name="checkout", last_seen_at=now)
    ApmSlo.objects.create(
        name="结算可用性",
        service=service,
        environment="production",
        sli_type="availability",
        objective=Decimal("99.900"),
        evaluation_window="rolling7d",
        is_enabled=True,
    )
    reliability = mocker.Mock(spec=DjangoApmReliabilityService)
    reliability.evaluate.return_value = SloEvaluation(
        current_rate=None,
        budget_remaining=None,
        data_state="no_data",
        started_at=now - timedelta(days=7),
        ended_at=now,
        reason="聚合库查询不可用",
    )

    failed = ApmDashboardService(reliability=reliability, now_fn=lambda: now).build(organization_id=10, window="1h")
    reliability.evaluate.return_value = SloEvaluation(
        current_rate=None,
        budget_remaining=None,
        data_state="no_data",
        started_at=now - timedelta(days=7),
        ended_at=now,
        reason="no_samples",
    )
    empty = ApmDashboardService(reliability=reliability, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert failed["slos"]["status"] == "failed"
    assert failed["slos"]["error"] == "聚合库查询不可用"
    assert empty["slos"]["status"] == "empty"


def test_dashboard_caps_red_queries_but_counts_all_visible_services_in_kpis(monkeypatch):
    now = timezone.now()
    red_by_name = {}
    for index in range(41):
        name = f"svc-{index}"
        _service(namespace=f"ns-{index}", name=name, last_seen_at=now - timedelta(seconds=index))
        red_by_name[name] = _red()
    store = StubMetricStore(red_by_name)
    materialized_counts = {ApmService: [], ApmServiceInstance: []}
    original_fetch_all = QuerySet._fetch_all

    def _fetch_all(self):
        original_fetch_all(self)
        if self.model in materialized_counts and self._result_cache is not None:
            materialized_counts[self.model].append(len(self._result_cache))

    monkeypatch.setattr(QuerySet, "_fetch_all", _fetch_all)

    payload = ApmDashboardService(metric_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert payload["empty"] is False
    assert len(store.service_red_calls) <= 40
    assert max(materialized_counts[ApmService] or [0]) <= 40
    assert max(materialized_counts[ApmServiceInstance] or [0]) <= 40
    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["application_count"] == 41
    assert payload["kpis"]["data"]["service_count"] == 41
    assert payload["aggregate_notice"] is None


def test_dashboard_keeps_both_environments_of_one_service_within_target_cap():
    now = timezone.now()
    checkout = _service(name="checkout", last_seen_at=now)
    ApmServiceInstance.objects.create(
        service=checkout,
        instance_id="checkout-2",
        normalized_instance_id="checkout-2",
        environment="staging",
        first_seen_at=now,
        last_seen_at=now,
    )
    red_by_name = {"checkout": _red()}
    for index in range(39):
        name = f"svc-{index}"
        _service(name=name, last_seen_at=now - timedelta(minutes=index + 1))
        red_by_name[name] = _red()
    store = StubMetricStore(red_by_name)

    payload = ApmDashboardService(metric_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    checkout_environments = {environment for name, environment in store.service_red_calls if name == "checkout"}
    assert payload["empty"] is False
    assert checkout_environments == {"production", "staging"}
    assert len(store.service_red_calls) <= 40


class _ExplodingRed:
    def service_red(self, query):
        raise TelemetryStoreUnavailable("聚合库查询不可用")


def _health_counts(payload):
    return {item["key"]: item["count"] for item in payload["health"]["data"]["buckets"]}


def test_dashboard_keeps_counts_and_marks_health_unknown_without_samples():
    now = timezone.now()
    _service(last_seen_at=now)
    traces = StubMetricStore({"checkout": _red()})
    red_store = StubMetricStore({"checkout": ServiceRed(None, None, None, None)})

    payload = ApmDashboardService(metric_store=traces, red_store=red_store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["service_count"] == 1
    assert payload["kpis"]["data"]["request_rate"] is None
    assert _health_counts(payload)["unknown"] == 1
    assert _health_counts(payload)["healthy"] == 0
    assert payload["top_error_rate"]["status"] == "empty"
    assert payload["top_p95"]["status"] == "empty"
    assert payload["health"]["status"] == "ok"
    assert traces.service_red_calls == []


def test_dashboard_aggregate_error_does_not_scan_traces():
    now = timezone.now()
    _service(last_seen_at=now)
    traces = StubMetricStore({"checkout": _red()})

    payload = ApmDashboardService(metric_store=traces, red_store=_ExplodingRed(), now_fn=lambda: now).build(organization_id=10, window="1h")

    assert traces.service_red_calls == []
    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["application_count"] == 1
    assert payload["kpis"]["data"]["request_rate"] is None
    assert payload["health"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_error_rate"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_p95"] == {"status": "failed", "error": "聚合库查询不可用"}


class _PartialAggregateRed:
    def service_red(self, query):
        if query.service_name == "payment":
            raise TelemetryStoreUnavailable("聚合库查询不可用")
        return _red(request_rate=10.0, error_rate=0.08, p95_ms=400.0)


def test_dashboard_top_and_health_fail_when_every_service_store_is_unavailable():
    now = timezone.now()
    _service(name="checkout", last_seen_at=now)
    _service(name="payment", last_seen_at=now)

    payload = ApmDashboardService(metric_store=StubMetricStore({}), red_store=_ExplodingRed(), now_fn=lambda: now).build(
        organization_id=10,
        window="1h",
    )

    assert payload["empty"] is False
    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["request_rate"] is None
    assert payload["kpis"]["data"]["error_request_rate"] is None
    assert payload["kpis"]["data"]["p95_ms"] is None
    assert payload["health"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_error_rate"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_p95"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["aggregate_notice"] is None


def test_dashboard_top_and_health_keep_successful_services_when_store_fails_partially():
    now = timezone.now()
    _service(name="checkout", last_seen_at=now)
    _service(name="payment", last_seen_at=now)

    payload = ApmDashboardService(
        metric_store=StubMetricStore({}),
        red_store=_PartialAggregateRed(),
        now_fn=lambda: now,
    ).build(organization_id=10, window="1h")

    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["request_rate"] == pytest.approx(10.0)
    assert payload["health"]["status"] == "ok"
    assert _health_counts(payload)["critical"] == 1
    assert _health_counts(payload)["unknown"] == 1
    assert payload["top_error_rate"]["status"] == "ok"
    assert [item["service_name"] for item in payload["top_error_rate"]["data"]["items"]] == ["checkout"]
    assert payload["top_p95"]["status"] == "ok"
    assert [item["service_name"] for item in payload["top_p95"]["data"]["items"]] == ["checkout"]
    assert payload["aggregate_notice"] is None


class _GroupedDashboardStore:
    def __init__(self, grouped):
        self.grouped = grouped
        self.grouped_calls = []
        self.service_red_calls = []

    def grouped_red(self, services, started_at, ended_at, *, include_overview, overview_points):
        del started_at, ended_at
        self.grouped_calls.append((tuple(services), include_overview, overview_points))
        if isinstance(self.grouped, Exception):
            if services:
                raise self.grouped
            return GroupedRed({}, frozenset(), None)
        return self.grouped

    def service_red(self, query):
        self.service_red_calls.append((query.service_name, query.environment))
        raise AssertionError(query.service_name)


def test_dashboard_grouped_read_covers_every_visible_service():
    now = timezone.now()
    points = SPARKLINE_POINTS["1h"]
    by_target = {}
    for index in range(59):
        name = f"svc-{index}"
        namespace = f"ns-{index}"
        _service(namespace=namespace, name=name, last_seen_at=now - timedelta(seconds=index))
        by_target[(namespace, name, "prod")] = ServiceRed(1.0, 0.0, 100.0, 110.0)
    _service(namespace="ns-59", name="svc-59", last_seen_at=now - timedelta(seconds=59))
    by_target[("ns-59", "svc-59", "unknown")] = ServiceRed(1.0, 0.5, 900.0, 950.0)
    _service(namespace="quiet-ns", name="quiet", last_seen_at=now)
    overview = GroupedRedOverview(
        request_rate=321.0,
        error_request_rate=0.4,
        p95_ms=250.0,
        request_trend=tuple(3.0 for _index in range(points)),
        error_trend=tuple(0.1 for _index in range(points)),
        p95_trend=tuple(250.0 for _index in range(points)),
        late_spans=7,
    )
    grouped = GroupedRed(
        by_target,
        frozenset({("ns-0", "svc-0"), ("ns-1", "svc-1")}),
        overview,
    )
    store = _GroupedDashboardStore(grouped)

    payload = ApmDashboardService(red_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    full_calls = [services for services, _overview, _points in store.grouped_calls if services]
    assert store.service_red_calls == []
    assert len(full_calls) == 1
    assert len(full_calls[0]) == 61
    assert store.grouped_calls[-1][1:] == (True, points)
    assert payload["aggregate_notice"] == {"late_spans": 7, "truncated_service_count": 2}
    assert payload["kpis"]["data"]["service_count"] == 61
    assert payload["kpis"]["data"]["request_rate"] == 321.0
    assert payload["kpis"]["data"]["error_request_rate"] == 0.4
    assert payload["kpis"]["data"]["p95_ms"] == 250.0
    assert payload["kpis"]["data"]["sparklines"]["request_rate"] == [3.0] * points
    assert payload["kpis"]["data"]["sparklines"]["p95_ms"] == [250.0] * points
    assert payload["health"]["data"]["total"] == 61
    assert _health_counts(payload) == {"healthy": 59, "warning": 0, "critical": 1, "unknown": 1}
    assert payload["top_error_rate"]["data"]["items"][0]["service_name"] == "svc-59"
    assert payload["top_error_rate"]["data"]["items"][0]["environment"] == ""
    assert payload["top_p95"]["data"]["items"][0]["service_name"] == "svc-59"
    assert payload["top_p95"]["data"]["items"][1]["environment"] == "prod"
    top_names = [item["service_name"] for item in payload["top_error_rate"]["data"]["items"]]
    assert "quiet" not in top_names


def test_dashboard_grouped_miss_keeps_the_forty_target_path(monkeypatch):
    now = timezone.now()
    red_by_name = {}
    for index in range(41):
        name = f"svc-{index}"
        _service(namespace=f"ns-{index}", name=name, last_seen_at=now - timedelta(seconds=index))
        red_by_name[name] = _red()
    store = StubMetricStore(red_by_name)
    store.grouped_calls = []

    def grouped_red(services, started_at, ended_at, *, include_overview, overview_points):
        del started_at, ended_at, include_overview, overview_points
        store.grouped_calls.append(tuple(services))
        return None

    store.grouped_red = grouped_red
    materialized_counts = {ApmService: []}
    original_fetch_all = QuerySet._fetch_all

    def _fetch_all(self):
        original_fetch_all(self)
        if self.model is ApmService and self._result_cache is not None:
            materialized_counts[ApmService].append(len(self._result_cache))

    monkeypatch.setattr(QuerySet, "_fetch_all", _fetch_all)

    payload = ApmDashboardService(red_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert store.grouped_calls == [()]
    assert len(store.service_red_calls) <= 40
    assert max(materialized_counts[ApmService] or [0]) <= 40
    assert payload["aggregate_notice"] is None
    assert payload["kpis"]["data"]["service_count"] == 41


def test_dashboard_grouped_failure_empties_red_without_scanning_targets():
    now = timezone.now()
    _service(name="checkout", last_seen_at=now)
    _service(name="payment", last_seen_at=now)
    store = _GroupedDashboardStore(TelemetryStoreUnavailable("聚合库查询不可用"))

    payload = ApmDashboardService(red_store=store, now_fn=lambda: now).build(organization_id=10, window="1h")

    assert store.service_red_calls == []
    assert payload["kpis"]["status"] == "ok"
    assert payload["kpis"]["data"]["application_count"] == 1
    assert payload["kpis"]["data"]["service_count"] == 2
    assert payload["kpis"]["data"]["request_rate"] is None
    assert payload["kpis"]["data"]["error_request_rate"] is None
    assert payload["kpis"]["data"]["p95_ms"] is None
    assert payload["health"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_error_rate"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["top_p95"] == {"status": "failed", "error": "聚合库查询不可用"}
    assert payload["aggregate_notice"] is None
