import importlib
import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.apps import apps
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.adapters.victoriatraces import VictoriaTracesTelemetryStore
from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmPolicy, ApmPolicyNotificationTarget, ApmPolicyTargetState, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import InstanceActivity, ServiceEndpointRed, ServiceMetricQuery, ServiceRed
from apps.apm.services.policies import policy_target_key
from apps.apm.tasks import dispatch_apm_policy_evaluations
from apps.apm.tests.helpers import bind_policy_organizations, create_application

backfill_policy_scope = importlib.import_module("apps.apm.migrations.0028_apmpolicy_scope").backfill_policy_scope

pytestmark = pytest.mark.django_db


def _service(name, organization=10, application=None):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        application=application,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    return service


def _policy(**updates):
    service = updates.pop("service", None) or _service(updates.get("name", "scope"))
    values = {
        "name": "范围策略",
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.ERROR_RATE,
        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "0.050000"}],
        "trigger_after": 1,
        "recover_after": 2,
        "metric_window": 5,
    }
    values.update(updates)
    policy = ApmPolicy.objects.create(**values)
    bind_policy_organizations(policy)
    return policy


def _payload(service, **updates):
    payload = {
        "name": "范围策略",
        "service_id": str(service.id),
        "organizations": [10],
        "environment": "production",
        "endpoints": [],
        "version_mode": "all",
        "versions": [],
        "metric_type": "error_rate",
        "evaluation_interval": 1,
        "metric_window": 5,
        "thresholds": [{"severity": "warning", "comparator": "gt", "value": "0.05"}],
        "trigger_after": 1,
        "recover_after": 2,
        "notification_targets": [],
    }
    payload.update(updates)
    return payload


class ScopeStore:
    def __init__(self, red=None):
        self.red = red or ServiceRed(10, 0.5, 100, 150, request_count=100)
        self.red_queries = []
        self.endpoint_queries = []
        self.endpoints = {}
        self.activities = []

    def service_red(self, query):
        self.red_queries.append(query)
        return self.red

    def service_endpoints(self, query, limit=100):
        self.endpoint_queries.append((query.service_name, limit))
        rows = self.endpoints.get(query.service_name, [])
        return tuple(ServiceEndpointRed(name, rate, None, None, None) for name, rate in rows[:limit])

    def instance_activity(self, query):
        return list(self.activities)


def _activity(service, instance_id, environment="production"):
    return InstanceActivity(
        service_namespace=service.namespace,
        service_name=service.name,
        instance_id=instance_id,
        environment=environment,
        version="v1",
        last_seen_at=datetime.now(UTC),
    )


def test_legacy_payload_keeps_single_service_and_infers_selected_endpoints(apm_api_client):
    service = _service("legacy-scope")
    empty = apm_api_client.post("/api/v1/apm/policies/", _payload(service, name="空端点"), format="json")
    selected = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(_service("legacy-selected"), name="手选", endpoints=["POST /checkout"]),
        format="json",
    )

    assert empty.status_code == 201
    assert empty.data["scope_mode"] == "service"
    assert empty.data["endpoint_mode"] == "service"
    assert empty.data["instance_mode"] == "all"
    assert empty.data["service_ids"] == []
    assert empty.data["service_id"] == str(service.id)
    assert selected.status_code == 201
    assert selected.data["endpoint_mode"] == "selected"
    assert selected.data["endpoints"] == ["POST /checkout"]


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"scope_mode": "services", "service_ids": []}, "service_ids"),
        ({"scope_mode": "application"}, "application"),
    ],
)
def test_scope_rules_reject_out_of_range_service_lists(apm_api_client, updates, field):
    service = _service("reject-scope")
    if updates.get("scope_mode") == "services" and updates.get("service_ids") == []:
        updates = {**updates, "service_ids": [str(service.id)]}
    response = apm_api_client.post("/api/v1/apm/policies/", _payload(service, **updates), format="json")

    assert response.status_code == 400
    assert field in response.data


def test_services_scope_accepts_two_to_twenty_and_mirrors_the_first(apm_api_client):
    first = _service("first-scope")
    second = _service("second-scope")
    accepted = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(first, scope_mode="services", service_ids=[str(second.id), str(first.id)], service_id=str(first.id)),
        format="json",
    )
    too_many = [str(_service(f"many-{index}").id) for index in range(21)]
    rejected = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(first, name="过多", scope_mode="services", service_ids=too_many),
        format="json",
    )

    assert accepted.status_code == 201
    assert accepted.data["service_id"] == str(second.id)
    assert accepted.data["service_ids"] == [str(second.id), str(first.id)]
    assert rejected.status_code == 400
    assert "service_ids" in rejected.data


def test_application_scope_mirrors_the_first_service_and_picks_up_new_services():
    application = create_application("shop-scope")
    first = _service("a-svc", application=application)
    second = _service("b-svc", application=application)
    policy = _policy(service=first, scope_mode=ApmPolicy.ScopeMode.APPLICATION, application=application)
    store = ScopeStore()
    service = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)

    service.evaluate(policy.id, evaluated_at=started)
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 2

    _service("c-svc", application=application)
    service.evaluate(policy.id, evaluated_at=started + timedelta(minutes=1))

    names = set(ApmPolicyTargetState.objects.filter(policy=policy).values_list("service__name", flat=True))
    assert names == {"a-svc", "b-svc", "c-svc"}
    assert policy.service_id == first.id
    assert second.id != first.id


def test_each_service_is_capped_at_100_and_invisible_services_are_skipped(mocker):
    visible = _service("visible-cap")
    hidden = _service("hidden-cap", organization=99)
    other = _service("other-cap")
    policy = _policy(
        service=visible,
        scope_mode=ApmPolicy.ScopeMode.SERVICES,
        service_ids=[str(visible.id), str(other.id), str(hidden.id)],
    )
    store = ScopeStore()
    store.endpoints = {
        visible.name: [(f"GET /v{index}", 200 - index) for index in range(120)],
        other.name: [(f"GET /o{index}", 80 - index) for index in range(60)],
        hidden.name: [("GET /secret", 999)],
    }
    policy.endpoint_mode = ApmPolicy.EndpointMode.ALL
    policy.save(update_fields=["endpoint_mode", "updated_at"])
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)

    preview = runner.dry_run(policy, evaluated_at=started)
    store.red_queries.clear()
    runner.evaluate(policy.id, evaluated_at=started)

    assert ApmPolicyTargetState.objects.filter(policy=policy, service=visible).count() == 100
    assert ApmPolicyTargetState.objects.filter(policy=policy, service=other).count() == 60
    assert ApmPolicyTargetState.objects.filter(policy=policy, service=hidden).count() == 0
    assert not any(query.service_name == hidden.name for query in store.red_queries)
    assert len([query for query in store.red_queries if query.service_name == visible.name]) == 100
    hidden_item = next(item for item in preview["items"] if item["service"] == hidden.name)
    assert hidden_item["verdict"] == "service_not_visible"
    assert preview["truncated"] is True
    assert preview["total_targets"] == 160
    delay = mocker.patch("apps.apm.tasks.evaluate_apm_policy.delay")
    dispatched = dispatch_apm_policy_evaluations.run()
    assert dispatched["dispatched"] == 2
    assert delay.call_count == 2
    assert {call.args[2] for call in delay.call_args_list} == {str(visible.id), str(other.id)}


def test_all_endpoints_admit_new_names_and_close_missing_ones_after_recover_after():
    service = _service("endpoints")
    policy = _policy(service=service, endpoint_mode=ApmPolicy.EndpointMode.ALL, recover_after=2)
    store = ScopeStore()
    store.endpoints[service.name] = [("GET /a", 10), ("GET /b", 9)]
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)

    runner.evaluate(policy.id, evaluated_at=started)
    assert set(ApmAlert.objects.filter(status=ApmAlert.Status.ACTIVE).values_list("endpoint", flat=True)) == {"GET /a", "GET /b"}

    store.endpoints[service.name] = [("GET /a", 10), ("GET /c", 8)]
    runner.evaluate(policy.id, evaluated_at=started + timedelta(minutes=1))
    assert ApmPolicyTargetState.objects.filter(policy=policy, endpoint="GET /c").exists()
    assert ApmPolicyTargetState.objects.get(policy=policy, endpoint="GET /b").missed_rounds == 1
    assert ApmAlert.objects.get(endpoint="GET /b").status == ApmAlert.Status.ACTIVE

    runner.evaluate(policy.id, evaluated_at=started + timedelta(minutes=2))

    assert not ApmPolicyTargetState.objects.filter(policy=policy, endpoint="GET /b").exists()
    assert ApmAlert.objects.get(endpoint="GET /b").status == ApmAlert.Status.RECOVERED
    assert ApmAlert.objects.get(endpoint="GET /a").status == ApmAlert.Status.ACTIVE
    assert store.endpoint_queries[0][1] == 100


def test_grouped_instances_filter_queries_and_label_alerts():
    service = _service("instances")
    policy = _policy(service=service, instance_mode=ApmPolicy.InstanceMode.GROUPED)
    ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=7,
        channel_name="告警中心",
        channel_type="nats",
        delivery_mode="alert_event_copy",
        recipient_mode="none",
        recipients=[],
    )
    store = ScopeStore()
    store.activities = [_activity(service, "pod-a"), _activity(service, "pod-b")]
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())

    preview = runner.dry_run(policy, evaluated_at=timezone.now())
    runner.evaluate(policy.id, evaluated_at=timezone.now().replace(second=0, microsecond=0))

    assert {item["instance"] for item in preview["items"]} == {"pod-a", "pod-b"}
    assert {query.instance_id for query in store.red_queries} == {"pod-a", "pod-b"}
    assert set(ApmAlert.objects.values_list("instance_id", flat=True)) == {"pod-a", "pod-b"}
    labels = ApmAlertOutbox.objects.get(event__alert__instance_id="pod-a").payload["labels"]
    assert labels["instance"] == "pod-a"


def test_endpoint_listing_failure_logs_one_warning_without_query_text(caplog):
    policy = _policy(endpoint_mode=ApmPolicy.EndpointMode.ALL)

    class FailingStore:
        def service_endpoints(self, query, limit=100):
            query_text = "QUERY_" + "SENTINEL"
            response_text = "RESPONSE_" + "SENTINEL"
            raise RuntimeError(f"query {query_text} body {response_text}")

        def service_red(self, query):
            raise AssertionError("failed endpoint listing must not query RED")

    runner = DjangoApmPolicyService(FailingStore(), InMemoryNotificationDispatcher())
    caplog.set_level(logging.DEBUG, logger="apm")

    with pytest.raises(TelemetryStoreUnavailable) as caught:
        runner.dry_run(policy, evaluated_at=timezone.now())

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_scope_failed policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (str(policy.id), "service_endpoints", "RuntimeError")
    rendered = logging.Formatter().format(record)
    assert "QUERY_SENTINEL" not in rendered
    assert "RESPONSE_SENTINEL" not in rendered
    assert "QUERY_SENTINEL" not in str(caught.value)
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 0


def test_scope_backfill_selects_endpoints_and_rewrites_target_keys():
    policy = _policy(endpoints=["POST /checkout"], endpoint_mode=ApmPolicy.EndpointMode.SERVICE)
    state = ApmPolicyTargetState.objects.create(
        policy=policy,
        target_key="legacy",
        endpoint="POST /checkout",
        version="v1",
    )

    backfill_policy_scope(apps, None)
    policy.refresh_from_db()
    state.refresh_from_db()

    assert policy.endpoint_mode == ApmPolicy.EndpointMode.SELECTED
    assert state.service_id == policy.service_id
    assert state.target_key == policy_target_key(policy.service_id, "POST /checkout", "v1", "")


def test_service_endpoints_and_instance_filter_use_entry_span_stats():
    store = VictoriaTracesTelemetryStore(endpoint="http://victoria-traces")
    captured = []

    def fake_stats(query, started_at, ended_at):
        captured.append(query)
        return [{"metric": {"name": "GET /a", "__name__": "requests"}, "value": [1, "4"]}]

    store._stats = fake_stats
    started = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
    query = ServiceMetricQuery(
        service_namespace="shop",
        service_name="demo-storefront",
        environment="production",
        started_at=started,
        ended_at=started + timedelta(minutes=5),
        instance_id="pod-1",
    )

    endpoints = store.service_endpoints(query, limit=100)
    store.service_red(query)

    assert endpoints[0].endpoint == "GET /a"
    assert "stats by (name) count() as requests" in captured[0]
    assert "limit 100" in captured[0]
    assert 'kind:in("2","5")' in captured[0]
    assert '`resource_attr:service.instance.id`:="pod-1"' in captured[0]
    assert '`resource_attr:service.instance.id`:="pod-1"' in captured[1]
    assert "limit 10" not in captured[0].replace("limit 100", "")
