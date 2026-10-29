import importlib
import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmEvent,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmPolicyTargetState,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed
from apps.apm.services.policy_conditions import anchor_from_policy, uses_legacy_evaluation
from apps.apm.tests.helpers import bind_policy_organizations

backfill_conditions = importlib.import_module("apps.apm.migrations.0027_apmpolicy_conditions").backfill_conditions

pytestmark = pytest.mark.django_db


def _service(name):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    return service


def _payload(service, **updates):
    payload = {
        "name": "条件策略",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "endpoints": [],
        "version_mode": "all",
        "versions": [],
        "metric_type": "p95",
        "evaluation_interval": 1,
        "metric_window": 5,
        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 3,
        "notification_targets": [],
    }
    payload.update(updates)
    return payload


def _policy(**updates):
    name = updates.pop("name", "conditions")
    service = updates.pop("service", None) or _service(name)
    values = {
        "name": name,
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.P95,
        "metric_window": 5,
        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 3,
    }
    values.update(updates)
    policy = ApmPolicy.objects.create(**values)
    bind_policy_organizations(policy)
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


def _regular(ref, metric, comparator, value, **updates):
    condition = {
        "ref": ref,
        "role": "regular",
        "metric_type": metric,
        "compare_mode": "absolute",
        "compare_offset_amount": None,
        "compare_value_kind": "",
        "min_request_count": None,
        "slow_threshold_ms": None,
        "apdex_threshold_ms": None,
        "thresholds": [{"severity": "warning", "comparator": comparator, "value": value}],
    }
    condition.update(updates)
    return condition


class _WindowStore:
    def __init__(self, current, baseline):
        self.current = current
        self.baseline = baseline
        self.calls = []
        self.current_end = None

    def service_red(self, query):
        self.calls.append(query.ended_at)
        if self.current_end is None:
            self.current_end = query.ended_at
        if query.ended_at == self.current_end:
            return self.current
        return self.baseline


def _red(rate=10, error_rate=0, requests=300):
    return ServiceRed(rate, error_rate, 1, 1, request_count=requests)


def _run(policy, store, rounds=1):
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)
    for index in range(rounds):
        service.evaluate(policy.id, evaluated_at=started + timedelta(minutes=index))
    return service


def test_residual_aggregation_on_a_stored_condition_stays_on_the_legacy_path():
    policy = _policy(name="residual-aggregation")
    stored = anchor_from_policy(policy)
    stored["aggregation"] = "max"
    policy.conditions = [stored]
    policy.save(update_fields=["conditions"])

    assert uses_legacy_evaluation(policy)


def test_legacy_payload_synthesizes_one_condition_and_keeps_mirror_columns(apm_api_client):
    service = _service("legacy-mirror")
    legacy = apm_api_client.post("/api/v1/apm/policies/", _payload(service, name="旧策略"), format="json")
    explicit = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            _service("explicit-one"),
            name="单条件",
            conditions=[_regular("a", "p95", "gt", "100")],
        ),
        format="json",
    )

    assert legacy.status_code == 201
    assert explicit.status_code == 201
    mirror_fields = (
        "metric_type",
        "compare_mode",
        "compare_offset_amount",
        "compare_value_kind",
        "min_request_count",
        "slow_threshold_ms",
        "apdex_threshold_ms",
        "thresholds",
    )
    assert "aggregation" not in legacy.data["conditions"][0]
    assert "aggregation" not in explicit.data["conditions"][0]
    assert len(legacy.data["conditions"]) == 1
    assert legacy.data["conditions"][0]["role"] == "regular"
    assert legacy.data["conditions"][0]["ref"] == "a"
    for field in mirror_fields:
        assert legacy.data[field] == explicit.data[field]
        assert legacy.data["conditions"][0][field] == legacy.data[field]


@pytest.mark.parametrize(
    ("updates", "message_field"),
    [
        ({"conditions": []}, "conditions"),
        (
            {
                "conditions": [
                    _regular("a", "p95", "gt", "1"),
                    _regular("b", "p95", "gt", "2"),
                    _regular("c", "throughput", "gt", "3"),
                    _regular("d", "error_count", "gt", "4"),
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "p95", "gt", "1"),
                    {"ref": "g1", "role": "guard", "metric_type": "error_count", "comparator": "gte", "value": "1"},
                    {"ref": "g2", "role": "guard", "metric_type": "error_count", "comparator": "gte", "value": "1"},
                    {"ref": "g3", "role": "guard", "metric_type": "error_count", "comparator": "gte", "value": "1"},
                ]
            },
            "conditions",
        ),
        (
            {"conditions": [_regular("a", "p95", "gt", "1"), _regular("a", "throughput", "gt", "2")]},
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "error_rate", "gt", "0.1"),
                    {
                        "ref": "g1",
                        "role": "guard",
                        "metric_type": "error_count",
                        "comparator": "gte",
                        "value": "1",
                        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "1"}],
                    },
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "throughput", "lte", "10", compare_mode="previous_window", compare_value_kind="percent"),
                    _regular("b", "error_rate", "gt", "0.1", compare_mode="offset_1h", compare_value_kind="percent"),
                    _regular("c", "p95", "gt", "1", compare_mode="offset_24h", compare_value_kind="percent"),
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "error_rate", "gt", "0.1"),
                    {
                        "ref": "g1",
                        "role": "guard",
                        "metric_type": "error_count",
                        "comparator": "gte",
                        "value": "1",
                        "compare_mode": "previous_window",
                    },
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "error_rate", "gt", "0.1"),
                    {"ref": "g1", "role": "guard", "metric_type": "no_traffic", "comparator": "lte", "value": "0"},
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "no_traffic", "lte", "0"),
                    _regular("b", "throughput", "gt", "1"),
                ]
            },
            "conditions",
        ),
        (
            {
                "conditions": [
                    _regular("a", "p95", "gt", "100"),
                    {**_regular("b", "throughput", "gt", "1"), "recovery_threshold": {"comparator": "lt", "value": "1"}},
                ]
            },
            "conditions",
        ),
    ],
)
def test_condition_rules_reject_each_forbidden_combination(apm_api_client, updates, message_field):
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(_service("reject-conditions"), **updates), format="json")

    assert response.status_code == 400
    assert message_field in response.data


def test_two_conditions_and_one_guard_are_accepted(apm_api_client):
    response = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            _service("accept-conditions"),
            metric_type="error_rate",
            thresholds=[{"severity": "critical", "comparator": "gt", "value": "0.99"}],
            conditions=[
                _regular(
                    "a",
                    "error_rate",
                    "gt",
                    "0.05",
                    thresholds=[
                        {"severity": "critical", "comparator": "gt", "value": "0.10"},
                        {"severity": "warning", "comparator": "gt", "value": "0.05"},
                    ],
                ),
                _regular(
                    "b",
                    "throughput",
                    "lte",
                    "-50",
                    compare_mode="previous_window",
                    compare_value_kind="percent",
                ),
                {"ref": "g1", "role": "guard", "metric_type": "request_count", "comparator": "gte", "value": "200"},
            ],
        ),
        format="json",
    )

    assert response.status_code == 201
    stored = ApmPolicy.objects.get(id=response.data["id"])
    assert stored.metric_type == "error_rate"
    assert stored.thresholds[0]["severity"] == "critical"
    assert stored.compare_mode == "absolute"
    assert [item["ref"] for item in stored.conditions] == ["a", "b", "g1"]


def test_shared_comparison_window_is_queried_once():
    policy = _policy(
        name="shared-window",
        metric_type="throughput",
        compare_mode="previous_window",
        compare_value_kind="percent",
        thresholds=[{"severity": "warning", "comparator": "lte", "value": "-50"}],
        conditions=[
            _regular("a", "throughput", "lte", "-50", compare_mode="previous_window", compare_value_kind="percent"),
            _regular("b", "error_rate", "gt", "10", compare_mode="previous_window", compare_value_kind="percent"),
        ],
    )
    store = _WindowStore(_red(10, 0.2), _red(30, 0.1))

    _run(policy, store)

    assert len(store.calls) == 2


def test_distinct_windows_query_current_plus_each_baseline():
    policy = _policy(
        name="two-windows",
        metric_type="throughput",
        compare_mode="previous_window",
        compare_value_kind="percent",
        thresholds=[{"severity": "warning", "comparator": "lte", "value": "-50"}],
        conditions=[
            _regular("a", "throughput", "lte", "-50", compare_mode="previous_window", compare_value_kind="percent"),
            _regular("b", "error_rate", "gt", "10", compare_mode="offset_1h", compare_value_kind="percent"),
        ],
    )
    store = _WindowStore(_red(10, 0.2), _red(30, 0.1))

    _run(policy, store)

    assert len(store.calls) == 3


@pytest.mark.parametrize(
    ("current_rate", "baseline_rate", "expect_alert"),
    [
        (10, 10, False),
        (800, 2000, False),
        (10, 30, True),
    ],
)
def test_throughput_floor_and_drop_follow_the_acceptance_cases(current_rate, baseline_rate, expect_alert):
    policy = _policy(
        name=f"floor-{current_rate}-{baseline_rate}",
        metric_type="throughput",
        thresholds=[{"severity": "warning", "comparator": "lte", "value": "16.67"}],
        conditions=[
            _regular("a", "throughput", "lte", "16.67"),
            _regular("b", "throughput", "lte", "-50", compare_mode="previous_window", compare_value_kind="percent"),
        ],
    )
    store = _WindowStore(_red(current_rate), _red(baseline_rate))

    _run(policy, store)
    alerts = ApmAlert.objects.filter(policy=policy)

    assert alerts.exists() is expect_alert
    if expect_alert:
        alert = alerts.get()
        assert alert.severity == "warning"
        assert alert.current_value == Decimal(str(current_rate))
        event = ApmEvent.objects.get(alert=alert, action=ApmEvent.Action.TRIGGERED)
        assert event.description.startswith("a: 当前")
        assert "b: 当前" in event.description
        labels = ApmAlertOutbox.objects.get(event=event).payload["labels"]
        assert "a_value" in labels
        assert "b_value" in labels
        assert event.snapshot.policy_snapshot["conditions"][1]["ref"] == "b"
        assert "b" in event.snapshot.evaluation_snapshot["condition_values"]


def test_lowest_matched_severity_wins_when_every_regular_hits():
    policy = _policy(
        name="lowest-level",
        metric_type="error_rate",
        thresholds=[
            {"severity": "critical", "comparator": "gt", "value": "0.10"},
            {"severity": "warning", "comparator": "gt", "value": "0.05"},
        ],
        conditions=[
            _regular(
                "a",
                "error_rate",
                "gt",
                "0.05",
                thresholds=[
                    {"severity": "critical", "comparator": "gt", "value": "0.10"},
                    {"severity": "warning", "comparator": "gt", "value": "0.05"},
                ],
            ),
            _regular("b", "throughput", "lte", "100"),
        ],
    )

    _run(policy, _WindowStore(_red(50, 0.12), _red(50, 0.12)))

    assert ApmAlert.objects.get(policy=policy).severity == "warning"


def test_unmatched_regular_does_not_fire():
    policy = _policy(
        name="and-miss",
        metric_type="throughput",
        thresholds=[{"severity": "warning", "comparator": "lte", "value": "16.67"}],
        conditions=[
            _regular("a", "throughput", "lte", "16.67"),
            _regular("b", "error_rate", "gt", "0.5"),
        ],
    )

    _run(policy, _WindowStore(_red(10, 0.12), _red(10, 0.12)))

    assert ApmAlert.objects.filter(policy=policy).count() == 0


def test_guard_blocks_then_allows_the_critical_level():
    conditions = [
        _regular(
            "a",
            "error_rate",
            "gt",
            "0.05",
            thresholds=[
                {"severity": "critical", "comparator": "gt", "value": "0.10"},
                {"severity": "warning", "comparator": "gt", "value": "0.05"},
            ],
        ),
        {"ref": "g1", "role": "guard", "metric_type": "request_count", "comparator": "gte", "value": "200"},
    ]
    policy = _policy(
        name="guard-level",
        metric_type="error_rate",
        thresholds=[
            {"severity": "critical", "comparator": "gt", "value": "0.10"},
            {"severity": "warning", "comparator": "gt", "value": "0.05"},
        ],
        conditions=conditions,
        recover_after=1,
    )
    service = DjangoApmPolicyService(_WindowStore(_red(10, 0.12, 150), _red()), InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)

    blocked = service.dry_run(policy, evaluated_at=evaluated_at)
    assert blocked["items"][0]["verdict"] == "guard_not_met"
    assert blocked["items"][0]["guards"] == [{"ref": "g1", "value": "150", "matched": False}]

    service.metric_store.current = _red(10, 0.12, 300)
    service.metric_store.current_end = None
    fired = service.dry_run(policy, evaluated_at=evaluated_at)
    assert fired["items"][0]["verdict"] == "would_trigger"
    assert fired["items"][0]["matched_threshold"]["severity"] == "critical"

    service.evaluate(policy.id, evaluated_at=evaluated_at)
    assert ApmAlert.objects.get(policy=policy).severity == "critical"


def test_guard_not_met_counts_toward_recovery():
    policy = _policy(
        name="guard-recover",
        metric_type="error_rate",
        thresholds=[{"severity": "critical", "comparator": "gt", "value": "0.10"}],
        conditions=[
            _regular("a", "error_rate", "gt", "0.10", thresholds=[{"severity": "critical", "comparator": "gt", "value": "0.10"}]),
            {"ref": "g1", "role": "guard", "metric_type": "request_count", "comparator": "gte", "value": "200"},
        ],
        recover_after=1,
    )
    store = _WindowStore(_red(10, 0.2, 300), _red())
    service = _run(policy, store)
    assert ApmAlert.objects.get(policy=policy).status == ApmAlert.Status.ACTIVE

    store.current = _red(10, 0.2, 150)
    store.current_end = None
    service.evaluate(policy.id, evaluated_at=timezone.now().replace(second=0, microsecond=0) + timedelta(minutes=5))

    assert ApmAlert.objects.get(policy=policy).status == ApmAlert.Status.RECOVERED


def test_missing_non_anchor_keeps_counters_and_the_active_alert():
    policy = _policy(
        name="hold-missing",
        metric_type="throughput",
        thresholds=[{"severity": "warning", "comparator": "lte", "value": "16.67"}],
        conditions=[
            _regular("a", "throughput", "lte", "16.67"),
            _regular("b", "throughput", "lte", "-50", compare_mode="previous_window", compare_value_kind="percent"),
        ],
        recover_after=3,
    )
    store = _WindowStore(_red(10), _red(30))
    service = _run(policy, store)
    state = ApmPolicyTargetState.objects.get(policy=policy)
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    state.consecutive_hits = 4
    state.consecutive_recoveries = 1
    state.hit_history = "10"
    state.save(update_fields=["consecutive_hits", "consecutive_recoveries", "hit_history"])

    store.baseline = ServiceRed(None, None, None, None)
    store.current_end = None
    evaluated_at = timezone.now().replace(second=0, microsecond=0) + timedelta(minutes=5)
    preview = service.dry_run(policy, evaluated_at=evaluated_at, saved_policy=policy)
    service.evaluate(policy.id, evaluated_at=evaluated_at)
    state.refresh_from_db()

    assert preview["items"][0]["verdict"] == "missing_condition_data"
    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.consecutive_hits == 4
    assert state.consecutive_recoveries == 1
    assert state.hit_history == "10"
    assert ApmAlert.objects.get(policy=policy).status == ApmAlert.Status.ACTIVE


def test_condition_query_failure_logs_one_warning_without_query_text(caplog):
    policy = _policy(
        name="condition-log",
        metric_type="throughput",
        thresholds=[{"severity": "warning", "comparator": "gt", "value": "1"}],
        conditions=[
            _regular("a", "throughput", "gt", "1"),
            _regular("b", "error_rate", "gt", "0.1"),
        ],
    )

    class FailingStore:
        def service_red(self, query):
            query_text = "QUERY_" + "SENTINEL"
            response_text = "RESPONSE_" + "SENTINEL"
            raise RuntimeError(f"query {query_text} body {response_text}")

    service = DjangoApmPolicyService(FailingStore(), InMemoryNotificationDispatcher())
    caplog.set_level(logging.DEBUG, logger="apm")
    before = ApmAlert.objects.count()

    with pytest.raises(TelemetryStoreUnavailable) as caught:
        service.dry_run(policy, evaluated_at=timezone.now())

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_condition_failed policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (str(policy.id), "conditions", "RuntimeError")
    rendered = logging.Formatter().format(record)
    assert "QUERY_SENTINEL" not in rendered
    assert "RESPONSE_SENTINEL" not in rendered
    assert "QUERY_SENTINEL" not in str(caught.value)
    assert ApmAlert.objects.count() == before
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 0


def test_backfill_copies_mirror_columns_into_one_regular_condition():
    kept = _policy(name="backfill-kept", conditions=[{"ref": "z", "role": "regular", "metric_type": "p95"}])
    empty = _policy(name="backfill-empty", metric_type="throughput", thresholds=[{"severity": "warning", "comparator": "gt", "value": "8"}])
    empty.conditions = []
    empty.save(update_fields=["conditions"])

    backfill_conditions(apps, None)
    kept.refresh_from_db()
    empty.refresh_from_db()

    assert kept.conditions[0]["ref"] == "z"
    assert empty.conditions[0]["ref"] == "a"
    assert empty.conditions[0]["role"] == "regular"
    assert empty.conditions[0]["metric_type"] == "throughput"
    assert empty.conditions[0]["thresholds"] == empty.thresholds
