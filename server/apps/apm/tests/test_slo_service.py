from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore, TelemetryStoreUnavailable
from apps.apm.models import ApmService, ApmServiceInstance, ApmSlo
from apps.apm.services import DjangoApmReliabilityService
from apps.apm.services.contracts import MetricDataState, SloMeasurement, SloMetricQuery

pytestmark = pytest.mark.django_db


def _slo(*, objective="99.000", enabled=True):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    return ApmSlo.objects.create(
        name="结算可用性",
        service=service,
        environment="production",
        sli_type="availability",
        objective=Decimal(objective),
        evaluation_window="rolling7d",
        is_enabled=enabled,
    )


def test_database_check_contracts_are_enforced_by_the_model_layer():
    now = timezone.now()
    with pytest.raises(IntegrityError, match="apm_service_name_not_empty"):
        ApmService.objects.create(
            namespace="shop",
            normalized_namespace="shop",
            name="",
            normalized_name="",
            first_seen_at=now,
            last_seen_at=now,
        )

    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    with pytest.raises(IntegrityError, match="apm_instance_id_not_empty"):
        ApmServiceInstance.objects.create(
            service=service,
            instance_id="",
            normalized_instance_id="",
            first_seen_at=now,
            last_seen_at=now,
        )
    with pytest.raises(IntegrityError, match="apm_slo_objective_range"):
        ApmSlo.objects.create(
            name="invalid objective",
            service=service,
            environment="production",
            sli_type="availability",
            objective=Decimal("0"),
            evaluation_window="rolling7d",
        )
    with pytest.raises(IntegrityError, match="apm_slo_latency_threshold_shape"):
        ApmSlo.objects.create(
            name="invalid latency shape",
            service=service,
            environment="production",
            sli_type="latency_p95",
            objective=Decimal("99"),
            latency_threshold_ms=None,
            evaluation_window="rolling7d",
        )
    with pytest.raises(IntegrityError, match="apm_slo_objective_range"):
        ApmSlo.objects.bulk_create(
            [
                ApmSlo(
                    name="invalid bulk objective",
                    service=service,
                    environment="production",
                    sli_type="availability",
                    objective=Decimal("0"),
                    evaluation_window="rolling7d",
                )
            ]
        )
    with pytest.raises(ValueError, match="逐条 save"):
        ApmSlo.objects.update(objective=Decimal("0"))


def test_slo_evaluation_hides_window_and_budget_math():
    slo = _slo()
    evaluated_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    query = SloMetricQuery(
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        endpoint="",
        sli_type="availability",
        latency_threshold_ms=None,
        started_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        ended_at=evaluated_at,
    )
    store = InMemoryMetricStore(
        slo_measurements=[
            (
                query,
                SloMeasurement(
                    compliance_percent=99.5,
                    good_rate=99.5,
                    total_rate=100,
                    data_state=MetricDataState.AVAILABLE,
                ),
            )
        ]
    )

    result = DjangoApmReliabilityService(store).evaluate(slo, evaluated_at=evaluated_at)

    assert result.current_rate == 99.5
    assert result.budget_remaining == 50.0
    assert result.data_state == "available"
    assert result.started_at == query.started_at


def test_slo_evaluation_preserves_no_data_and_disabled_semantics():
    slo = _slo()
    evaluated_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    query = SloMetricQuery(
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        endpoint="",
        sli_type="availability",
        latency_threshold_ms=None,
        started_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
        ended_at=evaluated_at,
    )
    store = InMemoryMetricStore(
        slo_measurements=[
            (
                query,
                SloMeasurement(
                    compliance_percent=None,
                    good_rate=None,
                    total_rate=None,
                    data_state=MetricDataState.NO_DATA,
                ),
            )
        ]
    )

    no_data = DjangoApmReliabilityService(store).evaluate(slo, evaluated_at=evaluated_at)
    slo.is_enabled = False
    disabled = DjangoApmReliabilityService(InMemoryMetricStore()).evaluate(slo, evaluated_at=evaluated_at)

    assert no_data.current_rate is None
    assert no_data.budget_remaining is None
    assert no_data.reason == "no_samples"
    assert disabled.reason == "disabled"


def _counting_store(measurement=None, *, error=None):
    calls = []

    def slo_measurement(query):
        calls.append(query)
        if error is not None:
            raise error
        return measurement

    store = InMemoryMetricStore()
    store.slo_measurement = slo_measurement
    return store, calls


def test_evaluate_many_reuses_one_measurement_for_identical_enabled_rules():
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    slos = [
        ApmSlo.objects.create(
            name=f"结算可用性 {index:02d}",
            service=service,
            environment="production",
            sli_type="availability",
            objective=Decimal("99.900"),
            evaluation_window="rolling30d",
            is_enabled=True,
        )
        for index in range(20)
    ]
    evaluated_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    store, calls = _counting_store(
        SloMeasurement(
            compliance_percent=99.5,
            good_rate=99.5,
            total_rate=100,
            data_state=MetricDataState.AVAILABLE,
        )
    )

    results = DjangoApmReliabilityService(store).evaluate_many(slos, evaluated_at=evaluated_at)

    assert len(calls) == 1
    assert [results[slo.id].current_rate for slo in slos] == [99.5] * 20


def test_evaluate_many_skips_disabled_and_keeps_failed_metadata():
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout",
        normalized_name="checkout",
        first_seen_at=now,
        last_seen_at=now,
    )
    disabled = ApmSlo.objects.create(
        name="已禁用",
        service=service,
        environment="production",
        sli_type="availability",
        objective=Decimal("99.900"),
        evaluation_window="rolling30d",
        is_enabled=False,
    )
    failed = ApmSlo.objects.create(
        name="遥测失败",
        service=service,
        environment="staging",
        sli_type="availability",
        objective=Decimal("99.900"),
        evaluation_window="rolling30d",
        is_enabled=True,
    )
    evaluated_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    store, calls = _counting_store(error=TelemetryStoreUnavailable("VictoriaTraces 查询不可用"))

    results = DjangoApmReliabilityService(store).evaluate_many([disabled, failed], evaluated_at=evaluated_at)

    assert len(calls) == 1
    assert results[disabled.id].reason == "disabled"
    assert results[disabled.id].current_rate is None
    assert results[failed.id].current_rate is None
    assert results[failed.id].reason
    assert "VictoriaTraces" in results[failed.id].reason


def test_slo_evaluation_treats_telemetry_unavailable_as_no_data():
    slo = _slo()
    evaluated_at = datetime(2026, 8, 3, 12, tzinfo=UTC)
    store = InMemoryMetricStore()
    store.slo_measurement = lambda query: (_ for _ in ()).throw(TelemetryStoreUnavailable("VictoriaTraces 查询不可用"))

    result = DjangoApmReliabilityService(store).evaluate(slo, evaluated_at=evaluated_at)

    assert result.current_rate is None
    assert result.data_state == "no_data"
    assert "VictoriaTraces" in result.reason
