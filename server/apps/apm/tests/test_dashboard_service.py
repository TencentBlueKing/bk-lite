from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.models import ApmAlert, ApmDeploymentEvent, ApmService, ApmServiceInstance, ApmServiceOrganization, ApmSlo
from apps.apm.services.contracts import ServiceRed, ServiceRedPoint, SloEvaluation, SloMeasurement
from apps.apm.services.dashboard import ApmDashboardService
from apps.apm.services.reliability import DjangoApmReliabilityService

pytestmark = pytest.mark.django_db


class StubMetricStore:
    def __init__(self, red_by_name: dict[str, ServiceRed], slo_rate: float | None = 99.9):
        self.red_by_name = red_by_name
        self.slo_rate = slo_rate
        self.fail_names: set[str] = set()
        self.deployment_release_calls = 0

    def service_red(self, query):
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
    assert payload["kpis"]["status"] == "empty"
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
