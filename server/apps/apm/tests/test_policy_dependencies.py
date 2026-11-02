import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryStoreUnavailable
from apps.apm.adapters.victoriatraces import VictoriaTracesTelemetryStore
from apps.apm.models import ApmAlert, ApmAlertOutbox, ApmPolicy, ApmPolicyNotificationTarget, ApmPolicyTargetState
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import DependencyMetricQuery, ServiceRed
from apps.apm.tests.test_policy_scope import _payload, _policy, _service

pytestmark = pytest.mark.django_db

MYSQL = {"channel": "database", "system": "mysql", "statement": "SELECT orders"}


def _dependency_policy(**updates):
    values = {
        "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
        "metric_type": ApmPolicy.MetricType.LATENCY_AVG,
        "thresholds": [{"severity": "critical", "comparator": "gt", "value": "300"}],
        "dependencies": [MYSQL],
        "trigger_after": 1,
        "recover_after": 2,
    }
    values.update(updates)
    return _policy(**values)


class DependencyStore:
    def __init__(self, red=None, rows=None):
        self.red = red or ServiceRed(1, 0, 10, 20, request_count=8, avg_ms=420)
        self.rows = list(rows or [])
        self.red_queries = []
        self.dependency_queries = []

    def service_red(self, query):
        self.red_queries.append(query)
        raise AssertionError("dependency targets must not query entry spans")

    def dependency_red(self, query):
        self.dependency_queries.append(query)
        return self.red

    def client_db_rollups(self, namespace, service_name, environment, started_at, ended_at):
        return list(self.rows)


def test_dependency_rules_reject_apdex_no_traffic_and_split_scope(apm_api_client):
    service = _service("dependency-rules")
    cases = [
        (
            {
                "target_kind": "dependency",
                "metric_type": "apdex",
                "apdex_threshold_ms": 100,
                "thresholds": [{"severity": "warning", "comparator": "lt", "value": "0.8"}],
            },
            "target_kind",
        ),
        (
            {"target_kind": "dependency", "metric_type": "no_traffic", "thresholds": [{"severity": "warning", "comparator": "lte", "value": "0"}]},
            "target_kind",
        ),
        ({"target_kind": "dependency", "endpoint_mode": "all"}, "target_kind"),
        ({"target_kind": "dependency", "instance_mode": "grouped"}, "target_kind"),
        ({"target_kind": "dependency", "dependencies": [{"channel": "queue", "system": "mysql", "statement": "SELECT"}]}, "dependencies"),
    ]
    for updates, field in cases:
        response = apm_api_client.post("/api/v1/apm/policies/", _payload(service, name=field, **updates), format="json")
        assert response.status_code == 400
        assert field in response.data


def test_dependency_list_accepts_empty_or_up_to_twenty(apm_api_client):
    service = _service("dependency-accept")
    picked = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(service, name="手选", target_kind="dependency", dependencies=[MYSQL]),
        format="json",
    )
    empty = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(service, name="全部", target_kind="dependency", dependencies=[]),
        format="json",
    )
    too_many = apm_api_client.post(
        "/api/v1/apm/policies/",
        _payload(
            service,
            name="过多",
            target_kind="dependency",
            dependencies=[{"channel": "database", "system": "mysql", "statement": f"q{index}"} for index in range(21)],
        ),
        format="json",
    )
    legacy = apm_api_client.post("/api/v1/apm/policies/", _payload(service, name="入口"), format="json")

    assert picked.status_code == 201
    assert picked.data["dependencies"] == [MYSQL]
    assert picked.data["endpoint_mode"] == "service"
    assert empty.status_code == 201
    assert empty.data["dependencies"] == []
    assert too_many.status_code == 400
    assert "dependencies" in too_many.data
    assert legacy.status_code == 201
    assert legacy.data["target_kind"] == "entry"
    assert legacy.data["dependencies"] == []


def test_empty_dependency_list_caps_at_forty_and_selected_list_queries_that_dependency():
    service = _service("dependency-cap")
    policy = _dependency_policy(service=service, dependencies=[])
    rows = [{"channel": "database", "system": "mysql", "statement": f"q{index}", "call_count": 1000 - index} for index in range(41)]
    store = DependencyStore(rows=rows)
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)

    preview = runner.dry_run(policy, evaluated_at=started)
    assert preview["total_targets"] == 40
    assert preview["truncated"] is True
    assert len(store.dependency_queries) == 20
    assert store.red_queries == []

    store.dependency_queries.clear()
    runner.evaluate(policy.id, evaluated_at=started)
    assert len(store.dependency_queries) == 40
    assert {query.statement for query in store.dependency_queries} == {f"q{index}" for index in range(40)}
    assert all(query.channel == "database" and query.system == "mysql" for query in store.dependency_queries)


def test_selected_dependency_renders_label_and_does_not_split_endpoints():
    service = _service("dependency-label")
    policy = _dependency_policy(service=service, endpoints=["POST /checkout"], endpoint_mode=ApmPolicy.EndpointMode.SELECTED)
    ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=7,
        channel_name="告警中心",
        channel_type="nats",
        delivery_mode="alert_event_copy",
        recipient_mode="none",
        recipients=[],
    )
    store = DependencyStore()
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())

    preview = runner.dry_run(policy, evaluated_at=timezone.now())
    runner.evaluate(policy.id, evaluated_at=timezone.now().replace(second=0, microsecond=0))

    assert preview["items"][0]["dependency"] == "mysql SELECT orders"
    assert preview["items"][0]["endpoint"] == ""
    assert len(store.dependency_queries) == 2
    labels = ApmAlertOutbox.objects.get().payload["labels"]
    assert labels["dependency"] == "mysql SELECT orders"
    assert labels["target_kind"] == "dependency"
    assert ApmAlert.objects.get().endpoint == ""


def test_missing_dependencies_recover_after_the_same_rounds_as_endpoints():
    service = _service("dependency-gone")
    policy = _dependency_policy(service=service, dependencies=[], recover_after=2)
    kept = {"channel": "database", "system": "mysql", "statement": "SELECT kept", "call_count": 10}
    gone = {"channel": "database", "system": "mysql", "statement": "SELECT gone", "call_count": 9}
    store = DependencyStore(rows=[kept, gone])
    runner = DjangoApmPolicyService(store, InMemoryNotificationDispatcher())
    started = timezone.now().replace(second=0, microsecond=0)

    runner.evaluate(policy.id, evaluated_at=started)
    store.rows = [kept, {"channel": "http", "system": "http", "statement": "GET /new", "call_count": 8}]
    runner.evaluate(policy.id, evaluated_at=started + timedelta(minutes=1))
    assert ApmPolicyTargetState.objects.get(policy=policy, dependency__statement="SELECT gone").missed_rounds == 1
    assert ApmAlert.objects.get(dependency__statement="SELECT gone").status == ApmAlert.Status.ACTIVE

    runner.evaluate(policy.id, evaluated_at=started + timedelta(minutes=2))

    assert not ApmPolicyTargetState.objects.filter(policy=policy, dependency__statement="SELECT gone").exists()
    assert ApmAlert.objects.get(dependency__statement="SELECT gone").status == ApmAlert.Status.RECOVERED
    assert ApmAlert.objects.get(dependency__statement="SELECT kept").status == ApmAlert.Status.ACTIVE
    assert ApmPolicyTargetState.objects.filter(policy=policy, dependency__statement="GET /new").exists()


def test_dependency_listing_failure_logs_one_warning_without_query_text(caplog):
    policy = _dependency_policy(dependencies=[])

    class FailingStore:
        def client_db_rollups(self, namespace, service_name, environment, started_at, ended_at):
            query_text = "QUERY_" + "SENTINEL"
            response_text = "RESPONSE_" + "SENTINEL"
            raise RuntimeError(f"query {query_text} body {response_text}")

        def dependency_red(self, query):
            raise AssertionError("failed listing must not query dependency RED")

    runner = DjangoApmPolicyService(FailingStore(), InMemoryNotificationDispatcher())
    caplog.set_level(logging.DEBUG, logger="apm")

    with pytest.raises(TelemetryStoreUnavailable) as caught:
        runner.dry_run(policy, evaluated_at=timezone.now())

    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_scope_failed policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (str(policy.id), "client_db_rollups", "RuntimeError")
    rendered = logging.Formatter().format(record)
    assert "QUERY_SENTINEL" not in rendered
    assert "RESPONSE_SENTINEL" not in rendered
    assert "QUERY_SENTINEL" not in str(caught.value)
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 0


def test_dependency_red_uses_client_span_stats():
    store = VictoriaTracesTelemetryStore(endpoint="http://victoria-traces")
    captured = []

    def fake_stats(query, started_at, ended_at):
        captured.append(query)
        return [{"metric": {"__name__": "requests"}, "value": [1, "4"]}]

    store._stats = fake_stats
    started = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
    red = store.dependency_red(
        DependencyMetricQuery(
            service_namespace="shop",
            service_name="demo-storefront",
            environment="production",
            started_at=started,
            ended_at=started + timedelta(minutes=5),
            channel="database",
            system="mysql",
            statement="SELECT orders",
            slow_threshold_ms=300,
        )
    )

    assert red.request_count == 4
    assert 'kind:="3"' in captured[0]
    assert 'kind:in("2","5")' not in captured[0]
    assert '`span_attr:db.system.name`:="mysql"' in captured[0]
    assert '`span_attr:db.statement`:="SELECT orders"' in captured[0]
    assert "count() as requests" in captured[0]
    assert "avg(duration) as avg_duration" in captured[0]
    assert "quantile(0.95, duration) as p95" in captured[0]
    assert 'count() if (status_code:="2") as errors' in captured[0]
    assert "count() if (duration:>300000000) as slow" in captured[0]
