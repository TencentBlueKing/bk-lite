import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import ApmAlert, ApmAlertMetricSnapshot, ApmAlertOutbox, ApmPolicy, ApmPolicyNotificationTarget, ApmSlo
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import MetricDataState, SloMeasurement
from apps.apm.tests.test_policy_scope import _payload, _policy, _service

pytestmark = pytest.mark.django_db

WHEN = datetime(2026, 8, 14, 2, 0, tzinfo=UTC)


def _measurement(compliance):
    if compliance is None:
        return SloMeasurement(None, None, None, MetricDataState.NO_DATA)
    return SloMeasurement(compliance, compliance, 10, MetricDataState.AVAILABLE)


class BurnStore:
    def __init__(self, by_minutes):
        self.by_minutes = by_minutes
        self.queries = []

    def slo_measurement(self, query):
        self.queries.append(query)
        minutes = int((query.ended_at - query.started_at).total_seconds() // 60)
        if minutes not in self.by_minutes:
            raise RuntimeError("QUERY_" + "SENTINEL")
        return self.by_minutes[minutes]


def _slo(**updates):
    service = _service("burn-owner")
    values = {
        "name": "结算可用性",
        "service": service,
        "environment": "production",
        "endpoint": "POST /orders",
        "sli_type": "availability",
        "objective": Decimal("99.900"),
        "evaluation_window": "rolling7d",
    }
    values.update(updates)
    return ApmSlo.objects.create(**values)


def _burn_policy(slo, **updates):
    values = {
        "service": slo.service,
        "environment": "staging",
        "metric_type": ApmPolicy.MetricType.SLO_BURN_RATE,
        "slo": slo,
        "burn_long_window_minutes": 60,
        "burn_short_window_minutes": 5,
        "thresholds": [{"severity": "critical", "comparator": "gte", "value": "14.4"}],
        "trigger_after": 1,
        "endpoints": [],
    }
    values.update(updates)
    policy = _policy(**values)
    ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=7,
        channel_name="告警中心",
        channel_type="nats",
        delivery_mode="alert_event_copy",
        recipient_mode="none",
        recipients=[],
    )
    return policy


def _evaluate(policy, store):
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=WHEN)
    return store


def test_fast_burn_fires_critical_when_both_windows_exceed_the_budget():
    slo = _slo()
    policy = _burn_policy(slo)
    store = _evaluate(policy, BurnStore({60: _measurement(98), 5: _measurement(97)}))

    assert [query.ended_at for query in store.queries] == [WHEN, WHEN]
    assert store.queries[0].started_at == WHEN - timedelta(minutes=60)
    assert store.queries[1].started_at == WHEN - timedelta(minutes=5)
    assert store.queries[0].endpoint == "POST /orders"
    assert store.queries[0].environment == "production"
    assert store.queries[0].service_name == slo.service.name
    alert = ApmAlert.objects.get()
    assert alert.status == ApmAlert.Status.ACTIVE
    assert alert.severity == "critical"
    assert alert.metric_type == "slo_burn_rate"
    assert alert.current_value == Decimal("20")
    labels = ApmAlertOutbox.objects.get().payload["labels"]
    assert labels["slo_name"] == "结算可用性"
    assert labels["burn_rate"] == "20"
    assert labels["budget_remaining"] == "0"
    assert ApmAlertOutbox.objects.get().payload["item"] == "slo_burn_rate"
    snapshot = ApmAlertMetricSnapshot.objects.get().snapshots[-1]
    assert snapshot["budget_remaining"] == "0"
    assert snapshot["value"] == "20"


def test_short_window_inside_budget_does_not_fire():
    slo = _slo()
    policy = _burn_policy(slo)
    _evaluate(policy, BurnStore({60: _measurement(98), 5: _measurement(99.95)}))

    assert ApmAlert.objects.count() == 0


def test_long_window_without_samples_is_no_data_and_short_window_is_insufficient():
    slo = _slo()
    policy = _burn_policy(slo)
    service = DjangoApmPolicyService(BurnStore({60: _measurement(None), 5: _measurement(97)}), InMemoryNotificationDispatcher())
    long_missing = service.test_query(policy, evaluated_at=WHEN)
    assert long_missing.data_state == MetricDataState.NO_DATA
    assert long_missing.breached is None

    short_missing = DjangoApmPolicyService(
        BurnStore({60: _measurement(98), 5: _measurement(None)}),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=WHEN)
    assert short_missing.data_state == MetricDataState.INSUFFICIENT_SAMPLES
    assert short_missing.breached is None


def test_severity_is_the_lower_of_the_two_windows():
    slo = _slo()
    policy = _burn_policy(
        slo,
        thresholds=[
            {"severity": "critical", "comparator": "gte", "value": "14.4"},
            {"severity": "warning", "comparator": "gte", "value": "6"},
        ],
    )
    result = DjangoApmPolicyService(
        BurnStore({60: _measurement(98.56), 5: _measurement(99.4)}),
        InMemoryNotificationDispatcher(),
    ).test_query(policy, evaluated_at=WHEN)

    assert result.breached is True
    assert result.threshold["severity"] == "warning"
    assert result.current_value == Decimal("14.4")
    assert result.baseline_value == Decimal("6")


def test_burn_query_failure_logs_one_warning_without_the_query(caplog):
    slo = _slo()
    policy = _burn_policy(slo)
    service = DjangoApmPolicyService(BurnStore({}), InMemoryNotificationDispatcher())
    caplog.set_level(logging.DEBUG, logger="apm")

    with pytest.raises(TelemetryStoreUnavailable):
        service.test_query(policy, evaluated_at=WHEN)

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_burn_failed policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (str(policy.id), "slo_burn_rate", "RuntimeError")
    formatted = logging.Formatter().format(record)
    assert "QUERY_SENTINEL" not in formatted


def test_deleting_an_slo_disables_its_policy_and_ends_the_active_alert(apm_api_client):
    slo = _slo()
    policy = _burn_policy(slo)
    _evaluate(policy, BurnStore({60: _measurement(98), 5: _measurement(97)}))
    assert ApmAlert.objects.get().status == ApmAlert.Status.ACTIVE

    deleted = apm_api_client.delete(f"/api/v1/apm/slos/{slo.id}/")

    assert deleted.status_code in {200, 204}
    policy.refresh_from_db()
    assert policy.is_enabled is False
    assert policy.slo_id is None
    assert ApmAlert.objects.get().status == ApmAlert.Status.RECOVERED


def test_burn_rate_rules_reject_scope_conditions_and_bad_windows(apm_api_client):
    slo = _slo()
    other = _policy(name="other-service").service
    base = {
        "metric_type": "slo_burn_rate",
        "slo": str(slo.id),
        "burn_long_window_minutes": 60,
        "burn_short_window_minutes": 5,
        "thresholds": [{"severity": "critical", "comparator": "gte", "value": "14.4"}],
    }
    cases = [
        (
            {
                "conditions": [
                    {
                        "ref": "a",
                        "role": "regular",
                        "metric_type": "error_rate",
                        "aggregation": "avg",
                        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "0.05"}],
                    }
                ]
            },
            "conditions",
        ),
        ({"scope_mode": "services", "service_ids": [str(slo.service_id), str(other.id)]}, "scope_mode"),
        ({"target_kind": "dependency", "dependencies": [{"channel": "database", "system": "mysql", "statement": "SELECT"}]}, "target_kind"),
        ({"compare_mode": "previous_window", "compare_value_kind": "percent"}, "compare_mode"),
        ({"min_request_count": 10}, "min_request_count"),
        ({"recovery_threshold": {"comparator": "lt", "value": "1"}}, "recovery_threshold"),
        ({"thresholds": [{"severity": "critical", "comparator": "lt", "value": "14.4"}]}, "thresholds"),
        ({"burn_short_window_minutes": 40}, "burn_short_window_minutes"),
        ({"slo": None}, "slo"),
    ]
    for updates, field in cases:
        response = apm_api_client.post(
            "/api/v1/apm/policies/",
            _payload(slo.service, name=field, **{**base, **updates}),
            format="json",
        )
        assert response.status_code == 400, updates
        assert field in response.data

    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(other, name="快燃", environment="staging", **base),
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["service_id"] == str(slo.service_id)
    assert created.data["environment"] == "production"
    assert created.data["endpoints"] == []
    assert created.data["burn_long_window_minutes"] == 60
    assert created.data["burn_short_window_minutes"] == 5
    assert str(created.data["slo"]) == str(slo.id)


def test_omitted_short_window_defaults_to_one_twelfth_of_the_long_window(apm_api_client):
    slo = _slo()
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            slo.service,
            name="默认短窗",
            metric_type="slo_burn_rate",
            slo=str(slo.id),
            burn_long_window_minutes=360,
            thresholds=[{"severity": "warning", "comparator": "gte", "value": "6"}],
        ),
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["burn_short_window_minutes"] == 30
