import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import ApmAlert, ApmEvent, ApmPolicy, ApmPolicyNotificationTarget, ApmPolicyTargetState, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed
from apps.apm.tests.helpers import bind_policy_organizations

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
        "name": "判定规则",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "endpoints": [],
        "version_mode": "all",
        "versions": [],
        "metric_type": "p95",
        "evaluation_interval": 1,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "trigger_after": 2,
        "recover_after": 2,
        "notification_targets": [],
    }
    payload.update(updates)
    return payload


def _policy(**updates):
    name = updates.get("name", "judge")
    service = _service(f"checkout-{name}")
    values = {
        "name": name,
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.P95,
        "metric_window": 5,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "100"}],
        "trigger_after": 1,
        "recover_after": 2,
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


class _Store:
    def __init__(self, red):
        self.red = red

    def service_red(self, query):
        return self.red


def _run(policy, samples):
    store = _Store(samples[0])
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)
    for index, red in enumerate(samples):
        store.red = red
        service.evaluate(policy.id, evaluated_at=started + timedelta(minutes=index))
    return ApmPolicyTargetState.objects.get(policy=policy)


def _red(p95, requests=20, rate=4):
    return ServiceRed(rate, 0, p95, p95, request_count=requests)


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"guard_conditions": []}, "guard_conditions"),
        ({"trigger_after": 3, "trigger_window": 2}, "trigger_window"),
        ({"trigger_window": 21}, "trigger_window"),
        ({"recovery_threshold": {"comparator": "gt", "value": "200"}}, "recovery_threshold"),
        (
            {
                "metric_type": "no_traffic",
                "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}],
                "recovery_threshold": {"comparator": "gt", "value": "1"},
            },
            "metric_type",
        ),
        (
            {
                "metric_type": "no_traffic",
                "thresholds": [{"severity": "error", "comparator": "lte", "value": "0"}],
                "trigger_window": 3,
            },
            "metric_type",
        ),
    ],
)
def test_judgment_rules_reject_illegal_combinations(apm_api_client, updates, field):
    name = "reject-" + str(abs(hash(json.dumps(updates, sort_keys=True, default=str))))
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(name), **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


def test_judgment_rules_accept_window_and_recovery_and_keep_legacy_payload(apm_api_client):
    service = _service("accept-judgment")
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            service,
            trigger_window=4,
            recovery_threshold={"comparator": "lt", "value": "80"},
        ),
        format="json",
    )
    legacy = apm_api_client.post("/api/v1/apm/policies/", _payload(_service("legacy-judgment"), name="旧判定"), format="json")

    assert created.status_code == 201
    assert "guard_conditions" not in created.data
    assert created.data["trigger_window"] == 4
    assert created.data["recovery_threshold"] == {"comparator": "lt", "value": "80"}
    assert legacy.status_code == 201
    assert "guard_conditions" not in legacy.data
    assert legacy.data["trigger_window"] is None
    assert legacy.data["recovery_threshold"] == {}


def test_trigger_window_counts_hits_ignores_undecidable_rounds_and_clears_after_firing():
    policy = _policy(name="window", trigger_after=2, trigger_window=3, recover_after=1)
    state = _run(policy, [_red(150), _red(10), _red(150)])

    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.hit_history == ""
    assert ApmEvent.objects.filter(alert__policy=policy, action=ApmEvent.Action.TRIGGERED).count() == 1


def test_insufficient_samples_do_not_append_hit_history():
    policy = _policy(name="samples", min_request_count=10, trigger_after=1)
    state = _run(policy, [_red(150, requests=2)])

    assert state.status == ApmPolicyTargetState.Status.NORMAL
    assert state.hit_history == ""
    assert state.consecutive_hits == 0


def test_hold_keeps_the_active_alert_and_records_an_info_point():
    policy = _policy(
        name="hold",
        trigger_after=1,
        recover_after=2,
        recovery_threshold={"comparator": "lt", "value": "50"},
    )
    state = _run(policy, [_red(150), _red(80)])
    alert = ApmAlert.objects.get(policy=policy)
    points = alert.metric_snapshot.snapshots

    assert state.status == ApmPolicyTargetState.Status.ACTIVE
    assert state.consecutive_hits == 0
    assert state.consecutive_recoveries == 0
    assert state.hit_history == "0"
    assert alert.status == ApmAlert.Status.ACTIVE
    assert points[-1]["data_state"] == "hold"
    assert points[-1]["type"] == "info"
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.RECOVERED).count() == 0


def test_crossing_the_recovery_line_counts_toward_recovery():
    policy = _policy(
        name="recover-line",
        trigger_after=1,
        recover_after=2,
        recovery_threshold={"comparator": "lt", "value": "50"},
    )
    state = _run(policy, [_red(150), _red(40), _red(40)])

    assert state.status == ApmPolicyTargetState.Status.NORMAL
    assert state.hit_history == ""
    assert ApmAlert.objects.get(policy=policy).status == ApmAlert.Status.RECOVERED


def test_dry_run_reports_hold_and_window_text_without_writing_state():
    window_policy = _policy(name="dry-window", trigger_after=2, trigger_window=4)
    window_policy.target_states.create(target_key="existing", endpoint="", version="", hit_history="000", status="normal")
    hold_policy = _policy(
        name="dry-hold",
        trigger_after=1,
        recovery_threshold={"comparator": "lt", "value": "50"},
    )
    hold_policy.target_states.create(
        target_key="active",
        endpoint="",
        version="",
        status=ApmPolicyTargetState.Status.ACTIVE,
        current_severity="error",
    )
    service = DjangoApmPolicyService(_Store(_red(150, rate=1)), InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)

    window = service.dry_run(window_policy, evaluated_at=evaluated_at, saved_policy=window_policy)
    hold = DjangoApmPolicyService(_Store(_red(80)), InMemoryNotificationDispatcher()).dry_run(
        hold_policy,
        evaluated_at=evaluated_at,
        saved_policy=hold_policy,
    )
    draft_band = DjangoApmPolicyService(_Store(_red(80)), InMemoryNotificationDispatcher()).dry_run(hold_policy, evaluated_at=evaluated_at)

    assert window["items"][0]["verdict"] == "would_trigger"
    assert window["items"][0]["hit_history_text"] == "近 4 轮命中 1 / 2"
    assert "guards" not in window["items"][0]
    assert hold["items"][0]["verdict"] == "hold"
    assert draft_band["items"][0]["verdict"] == "ok"
    assert ApmAlert.objects.filter(policy__in=[window_policy, hold_policy]).count() == 0
    assert window_policy.target_states.get().hit_history == "000"


def test_legacy_absolute_policy_still_triggers_on_consecutive_hits():
    policy = _policy(name="legacy-eval", trigger_after=2, recover_after=1)
    state = _run(policy, [_red(150), _red(150), _red(10)])

    assert state.status == ApmPolicyTargetState.Status.NORMAL
    assert ApmAlert.objects.get(policy=policy).status == ApmAlert.Status.RECOVERED
    assert state.hit_history == ""
