from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryMetricStore
from apps.apm.models import ApmService, ApmSlo
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
