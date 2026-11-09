"""当前窗按目标分组取回的 RED 必须与逐目标查询一致。"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.adapters.errors import TelemetryGroupedReadFallback, TelemetryStoreUnavailable
from apps.apm.adapters.span_memory import InMemorySpanMetricStore, MemorySpan
from apps.apm.models import ApmAlert, ApmAlertMetricSnapshot, ApmPolicy, ApmPolicyTargetState, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import (
    GROUPED_RED_INSTANCE,
    GROUPED_RED_NAME,
    GROUPED_RED_VERSION,
    DependencyMetricQuery,
    GroupedDependencyRedQuery,
    GroupedServiceRedQuery,
    ServiceMetricQuery,
)
from apps.apm.tests.helpers import bind_policy_organizations

WINDOW_START = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
WINDOW_END = WINDOW_START + timedelta(minutes=1)


def _minute() -> datetime:
    return timezone.now().replace(second=0, microsecond=0)


def _service_row(name: str) -> ApmService:
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


def _policy(service: ApmService, **updates) -> ApmPolicy:
    name = updates.pop("name", f"分组策略-{service.name}")
    values = {
        "name": name,
        "service": service,
        "environment": "production",
        "metric_type": ApmPolicy.MetricType.ERROR_RATE,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
        "trigger_after": 1,
        "recover_after": 1,
        "metric_window": 1,
        "evaluation_interval": 1,
        "slow_threshold_ms": 200,
        "apdex_threshold_ms": 200,
    }
    values.update(updates)
    policy = ApmPolicy.objects.create(**values)
    bind_policy_organizations(policy)
    return policy


def _live(moment: datetime, **overrides) -> MemorySpan:
    values = {
        "trace_id": "trace",
        "span_id": "span",
        "started_at": moment - timedelta(seconds=30),
        "duration_ms": 100.0,
        "service_namespace": "shop",
        "service_name": "checkout",
        "environment": "production",
        "name": "GET /ok",
        "kind": "server",
        "status": "ok",
        "version": "",
        "instance_id": "",
        "attributes": {},
    }
    values.update(overrides)
    return MemorySpan(**values)


class RecordingStore:
    def __init__(self, spans, *, grouped: bool = True, unique_span_limit: int | None = None):
        self.inner = InMemorySpanMetricStore(spans, unique_span_limit=unique_span_limit)
        self.calls: list[str] = []
        self.error: BaseException | None = None
        if not grouped:
            self.service_red_grouped = None
            self.dependency_red_grouped = None

    @property
    def spans(self):
        return self.inner.spans

    @spans.setter
    def spans(self, value):
        self.inner.spans = list(value)

    def service_red(self, query):
        self.calls.append("service_red")
        return self.inner.service_red(query)

    def service_red_grouped(self, query):
        self.calls.append("service_red_grouped")
        return self.inner.service_red_grouped(query)

    def service_endpoints(self, query, limit=100):
        self.calls.append("service_endpoints")
        return self.inner.service_endpoints(query, limit)

    def instance_activity(self, query):
        self.calls.append("instance_activity")
        return self.inner.instance_activity(query)

    def dependency_red(self, query):
        self.calls.append("dependency_red")
        return self.inner.dependency_red(query)

    def dependency_red_grouped(self, query):
        self.calls.append("dependency_red_grouped")
        return self.inner.dependency_red_grouped(query)

    def client_db_rollups(self, namespace, service_name, environment, started_at, ended_at):
        self.calls.append("client_db_rollups")
        return self.inner.client_db_rollups(namespace, service_name, environment, started_at, ended_at)


class UnavailableGroupedStore(RecordingStore):
    def service_red_grouped(self, query):
        self.calls.append("service_red_grouped")
        self.error = TelemetryStoreUnavailable("grouped down")
        raise self.error

    def dependency_red_grouped(self, query):
        self.calls.append("dependency_red_grouped")
        self.error = TelemetryStoreUnavailable("grouped down")
        raise self.error


class ReadingPolicyService(DjangoApmPolicyService):
    def __init__(self, metric_store, dispatcher):
        super().__init__(metric_store, dispatcher)
        self.reads = []

    def _read_window(self, policy, **kwargs):
        red = super()._read_window(policy, **kwargs)
        if kwargs.get("include_endpoints"):
            self.reads.append((kwargs.get("endpoint") or "", kwargs.get("version") or "", kwargs.get("instance_id") or "", red.top_endpoints))
        return red


_SERVICE_SEQUENCE = 0


def _next_service(prefix: str) -> ApmService:
    global _SERVICE_SEQUENCE
    _SERVICE_SEQUENCE += 1
    return _service_row(f"{prefix}-{_SERVICE_SEQUENCE}")


def _stamp(service: ApmService, spans) -> list[MemorySpan]:
    return [replace(span, service_namespace=service.namespace, service_name=service.name) for span in spans]


def _run_pair(*, policy_kwargs, spans_by_minute, moments):
    service = _next_service("pair")
    grouped_store = RecordingStore([])
    plain_store = RecordingStore([], grouped=False)
    grouped_policy = _policy(service, name=f"grouped-{service.name}", **policy_kwargs)
    plain_policy = _policy(service, name=f"plain-{service.name}", **policy_kwargs)
    grouped_runner = DjangoApmPolicyService(grouped_store, InMemoryNotificationDispatcher())
    plain_runner = DjangoApmPolicyService(plain_store, InMemoryNotificationDispatcher())
    for moment, spans in zip(moments, spans_by_minute, strict=True):
        grouped_store.spans = _stamp(service, spans)
        plain_store.spans = _stamp(service, spans)
        grouped_runner.evaluate(grouped_policy.id, evaluated_at=moment)
        plain_runner.evaluate(plain_policy.id, evaluated_at=moment)
    return grouped_policy, plain_policy, grouped_store


def _fingerprint(policy_id):
    states = [
        {
            "endpoint": state.endpoint,
            "version": state.version,
            "instance_id": state.instance_id,
            "dependency": state.dependency,
            "status": state.status,
            "hits": state.consecutive_hits,
            "recoveries": state.consecutive_recoveries,
            "no_data": state.consecutive_no_data,
            "severity": state.current_severity,
        }
        for state in ApmPolicyTargetState.objects.filter(policy_id=policy_id).order_by("endpoint", "version", "instance_id", "target_key")
    ]
    alerts = []
    for alert in ApmAlert.objects.filter(policy_id=policy_id).order_by("endpoint", "version", "instance_id", "dependency", "id"):
        snapshot = ApmAlertMetricSnapshot.objects.filter(alert=alert).first()
        points = []
        if snapshot is not None:
            points = [
                {
                    "type": item.get("type"),
                    "value": item.get("value"),
                    "current_value": item.get("current_value"),
                    "baseline_value": item.get("baseline_value"),
                    "data_state": item.get("data_state"),
                }
                for item in snapshot.snapshots
            ]
        alerts.append(
            {
                "endpoint": alert.endpoint,
                "version": alert.version,
                "instance_id": alert.instance_id,
                "dependency": alert.dependency,
                "status": alert.status,
                "points": points,
                "evidence": [
                    {
                        "action": item.action,
                        "series": item.pending_payload.get("series"),
                        "baseline_series": item.pending_payload.get("baseline_series"),
                    }
                    for item in alert.snapshots.order_by("occurred_at", "id")
                ],
            }
        )
    return {"states": states, "alerts": alerts}


def _assert_same_outcome(left_id, right_id, *, require_recovery=True):
    left = _fingerprint(left_id)
    right = _fingerprint(right_id)
    assert left == right
    assert left["alerts"]
    assert any(item["evidence"] and item["evidence"][0]["series"] for item in left["alerts"])
    if require_recovery:
        assert any(item["status"] == ApmAlert.Status.RECOVERED for item in left["alerts"])


def _call_counts(target_count: int, moment: datetime) -> dict[str, int]:
    service = _next_service("calls")
    spans = [
        _live(moment, trace_id=f"t{index}", span_id=f"s{index}", name=f"GET /{index}", status="error" if index == 0 else "ok")
        for index in range(target_count)
    ]
    store = RecordingStore(_stamp(service, spans))
    policy = _policy(service, endpoint_mode=ApmPolicy.EndpointMode.ALL, endpoints=[])
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)
    names = ("service_red", "service_red_grouped", "service_endpoints", "dependency_red", "dependency_red_grouped")
    return {name: store.calls.count(name) for name in names}


def _span(**overrides) -> MemorySpan:
    values = {
        "trace_id": "trace-1",
        "span_id": "span-1",
        "started_at": WINDOW_START + timedelta(seconds=1),
        "duration_ms": 100.0,
        "service_namespace": "shop",
        "service_name": "checkout",
        "environment": "production",
        "name": "GET /a",
        "kind": "server",
        "status": "ok",
        "version": "v1",
        "instance_id": "pod-a",
        "attributes": {},
    }
    values.update(overrides)
    return MemorySpan(**values)


def _entry_spans() -> list[MemorySpan]:
    return [
        _span(trace_id="trace-a", span_id="span-a", duration_ms=80),
        _span(trace_id="trace-a", span_id="span-a", duration_ms=250),
        _span(
            trace_id="trace-b",
            span_id="span-b",
            started_at=WINDOW_START + timedelta(seconds=20),
            duration_ms=400,
            status="error",
        ),
        _span(
            trace_id="trace-c",
            span_id="span-c",
            name="GET /b",
            version="v2",
            instance_id="pod-b",
            duration_ms=50,
            started_at=WINDOW_START + timedelta(seconds=5),
        ),
        _span(trace_id="trace-other", span_id="span-other", service_name="catalog", name="GET /other"),
        _span(trace_id="trace-client", span_id="span-client", kind="client", name="SELECT orders"),
    ]


def _without_top(red):
    return replace(red, top_endpoints=())


def test_grouped_entry_red_matches_per_target_counts_and_trend():
    store = InMemorySpanMetricStore(_entry_spans())
    query = GroupedServiceRedQuery(
        service_namespace="shop",
        service_name="checkout",
        environment="production",
        started_at=WINDOW_START,
        ended_at=WINDOW_END,
        group_by=(GROUPED_RED_NAME, GROUPED_RED_VERSION, GROUPED_RED_INSTANCE),
        include_breakdown=True,
        slow_threshold_ms=200,
        apdex_threshold_ms=200,
    )
    grouped = store.service_red_grouped(query)

    checkout = grouped[("GET /a", "v1", "pod-a")]
    assert checkout.request_count == 2
    assert checkout.error_count == 1
    assert checkout.error_rate == 0.5
    assert checkout.request_rate == 2 / 60
    assert checkout.slow_count == 2
    assert checkout.satisfied_count == 0
    assert checkout.tolerating_count == 2
    assert checkout.p50_ms == 250
    assert checkout.p95_ms == 400
    assert checkout.max_ms == 400
    assert [point.request_count for point in checkout.timeseries] == [1, 1]
    assert [point.error_count for point in checkout.timeseries] == [0, 1]
    assert checkout.timeseries[0].slow_count == 1
    assert checkout.timeseries[1].p95_ms == 400

    other = grouped[("GET /b", "v2", "pod-b")]
    assert other.request_count == 1
    assert other.error_count == 0
    assert other.slow_count == 0
    assert other.satisfied_count == 1
    assert other.tolerating_count == 0
    assert other.p95_ms == 50

    assert set(grouped) == {("GET /a", "v1", "pod-a"), ("GET /b", "v2", "pod-b")}
    for key, red in grouped.items():
        endpoint, version, instance_id = key
        direct = store.service_red(
            ServiceMetricQuery(
                service_namespace="shop",
                service_name="checkout",
                environment="production",
                started_at=WINDOW_START,
                ended_at=WINDOW_END,
                include_breakdown=True,
                include_endpoints=True,
                endpoint=endpoint,
                version=version,
                instance_id=instance_id,
                slow_threshold_ms=200,
                apdex_threshold_ms=200,
            )
        )
        assert _without_top(direct) == _without_top(red)
        assert direct.top_endpoints[0].endpoint == endpoint
        assert direct.top_endpoints[0].request_rate == red.request_rate
        assert direct.top_endpoints[0].error_rate == red.error_rate
        assert direct.top_endpoints[0].p95_ms == red.p95_ms


def test_grouped_dependency_red_matches_database_and_cache_targets():
    spans = [
        _span(
            trace_id="trace-db",
            span_id="span-db",
            kind="client",
            name="SELECT",
            duration_ms=80,
            attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
        ),
        _span(
            trace_id="trace-db",
            span_id="span-db",
            kind="client",
            name="SELECT",
            duration_ms=100,
            attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
        ),
        _span(
            trace_id="trace-users",
            span_id="span-users",
            kind="client",
            name="SELECT",
            duration_ms=300,
            status="error",
            attributes={"db.system.name": "mysql", "db.statement": "SELECT users"},
        ),
        _span(
            trace_id="trace-cache",
            span_id="span-cache",
            kind="client",
            name="GET",
            duration_ms=20,
            attributes={"db.system.name": "redis", "db.statement": "GET cart"},
        ),
        _span(trace_id="trace-entry", span_id="span-entry", kind="server", name="GET /a"),
    ]
    store = InMemorySpanMetricStore(spans)
    grouped = store.dependency_red_grouped(
        GroupedDependencyRedQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=WINDOW_START,
            ended_at=WINDOW_END,
            include_breakdown=True,
            slow_threshold_ms=200,
            apdex_threshold_ms=100,
        )
    )

    orders = grouped[("database", "mysql", "SELECT orders")]
    assert orders.request_count == 1
    assert orders.error_count == 0
    assert orders.max_ms == 100
    assert orders.slow_count == 0
    assert orders.satisfied_count == 1
    users = grouped[("database", "mysql", "SELECT users")]
    assert users.request_count == 1
    assert users.error_rate == 1
    assert users.slow_count == 1
    assert users.satisfied_count == 0
    cache = grouped[("outbound", "redis", "GET cart")]
    assert cache.request_count == 1
    assert cache.slow_count == 0
    assert set(grouped) == {
        ("database", "mysql", "SELECT orders"),
        ("database", "mysql", "SELECT users"),
        ("outbound", "redis", "GET cart"),
    }
    for (channel, system, statement), red in grouped.items():
        direct = store.dependency_red(
            DependencyMetricQuery(
                service_namespace="shop",
                service_name="checkout",
                environment="production",
                started_at=WINDOW_START,
                ended_at=WINDOW_END,
                channel=channel,
                system=system,
                statement=statement,
                include_breakdown=True,
                slow_threshold_ms=200,
                apdex_threshold_ms=100,
            )
        )
        assert direct == red


def test_http_dependency_filter_overlaps_targets_so_grouping_cannot_reuse_it():
    """现有 HTTP 过滤用 http.route:*，一个带路由的 Span 会命中每个 HTTP 目标。"""

    store = InMemorySpanMetricStore(
        [
            _span(
                trace_id="trace-users",
                span_id="span-users",
                kind="client",
                name="GET",
                duration_ms=100,
                attributes={"http.request.method": "GET", "http.route": "/users", "peer.service": "billing"},
            ),
            _span(
                trace_id="trace-orders",
                span_id="span-orders",
                kind="client",
                name="POST",
                duration_ms=200,
                attributes={"http.request.method": "POST", "http.route": "/orders", "peer.service": "billing"},
            ),
        ]
    )
    grouped = store.dependency_red_grouped(
        GroupedDependencyRedQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=WINDOW_START,
            ended_at=WINDOW_END,
        )
    )
    direct = store.dependency_red(
        DependencyMetricQuery(
            service_namespace="shop",
            service_name="checkout",
            environment="production",
            started_at=WINDOW_START,
            ended_at=WINDOW_END,
            channel="http",
            system="billing",
            statement="GET /users",
        )
    )

    assert grouped[("http", "billing", "GET /users")].request_count == 1
    assert direct.request_count == 2


@pytest.mark.django_db
def test_selected_endpoints_match_per_target_trigger_recovery_and_evidence():
    moment = _minute()
    later = moment + timedelta(minutes=1)
    grouped, plain, store = _run_pair(
        policy_kwargs={
            "endpoints": ["GET /pay", "GET /ok", "GET /quiet"],
            "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
        },
        spans_by_minute=[
            [
                _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error", duration_ms=400),
                _live(moment, trace_id="ok", span_id="ok", name="GET /ok", duration_ms=50),
            ],
            [
                _live(later, trace_id="pay2", span_id="pay2", name="GET /pay", duration_ms=50),
                _live(later, trace_id="ok2", span_id="ok2", name="GET /ok", duration_ms=50),
            ],
        ],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped") == 2
    recovered = _fingerprint(grouped.id)["alerts"]
    assert len(recovered) == 1
    assert recovered[0]["endpoint"] == "GET /pay"
    assert recovered[0]["status"] == ApmAlert.Status.RECOVERED
    assert [item["action"] for item in recovered[0]["evidence"]] == ["triggered", "recovered"]
    assert recovered[0]["evidence"][0]["series"]
    states = {item["endpoint"]: item for item in _fingerprint(grouped.id)["states"]}
    assert states["GET /quiet"]["no_data"] == 2
    assert states["GET /ok"]["status"] == ApmPolicyTargetState.Status.NORMAL


@pytest.mark.django_db
def test_all_endpoints_versions_instances_and_dependencies_match_per_target():
    moment = _minute()
    later = moment + timedelta(minutes=1)
    cases = {
        "all-endpoints": (
            {"endpoint_mode": ApmPolicy.EndpointMode.ALL, "endpoints": []},
            [
                [
                    _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error"),
                    _live(moment, trace_id="ok", span_id="ok", name="GET /ok"),
                ],
                [
                    _live(later, trace_id="pay2", span_id="pay2", name="GET /pay"),
                    _live(later, trace_id="ok2", span_id="ok2", name="GET /ok"),
                ],
            ],
        ),
        "versions": (
            {"version_mode": ApmPolicy.VersionMode.SPECIFIC, "versions": ["v1", "v2"]},
            [
                [
                    _live(moment, trace_id="v1", span_id="v1", version="v1", status="error", name="GET /a"),
                    _live(moment, trace_id="v1b", span_id="v1b", version="v1", status="error", name="GET /b"),
                    _live(moment, trace_id="v2", span_id="v2", version="v2", name="GET /c"),
                ],
                [
                    _live(later, trace_id="v1c", span_id="v1c", version="v1", name="GET /a"),
                    _live(later, trace_id="v2b", span_id="v2b", version="v2", name="GET /c"),
                ],
            ],
        ),
        "instances": (
            {"instance_mode": ApmPolicy.InstanceMode.GROUPED},
            [
                [
                    _live(moment, trace_id="ia", span_id="ia", instance_id="pod-a", status="error"),
                    _live(moment, trace_id="ib", span_id="ib", instance_id="pod-b"),
                ],
                [
                    _live(later, trace_id="ia2", span_id="ia2", instance_id="pod-a"),
                    _live(later, trace_id="ib2", span_id="ib2", instance_id="pod-b"),
                ],
            ],
        ),
        "dependencies": (
            {
                "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
                "dependencies": [
                    {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                    {"channel": "database", "system": "mysql", "statement": "SELECT users"},
                    {"channel": "outbound", "system": "redis", "statement": "GET cart"},
                ],
            },
            [
                [
                    _live(
                        moment,
                        trace_id="orders",
                        span_id="orders",
                        kind="client",
                        name="SELECT",
                        status="error",
                        attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
                    ),
                    _live(
                        moment,
                        trace_id="users",
                        span_id="users",
                        kind="client",
                        name="SELECT",
                        attributes={"db.system.name": "mysql", "db.statement": "SELECT users"},
                    ),
                    _live(
                        moment,
                        trace_id="cache",
                        span_id="cache",
                        kind="client",
                        name="GET",
                        attributes={"db.system.name": "redis", "db.statement": "GET cart"},
                    ),
                ],
                [
                    _live(
                        later,
                        trace_id="orders2",
                        span_id="orders2",
                        kind="client",
                        name="SELECT",
                        attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
                    ),
                    _live(
                        later,
                        trace_id="users2",
                        span_id="users2",
                        kind="client",
                        name="SELECT",
                        attributes={"db.system.name": "mysql", "db.statement": "SELECT users"},
                    ),
                    _live(
                        later,
                        trace_id="cache2",
                        span_id="cache2",
                        kind="client",
                        name="GET",
                        attributes={"db.system.name": "redis", "db.statement": "GET cart"},
                    ),
                ],
            ],
        ),
    }
    for name, (policy_kwargs, spans_by_minute) in cases.items():
        grouped, plain, store = _run_pair(policy_kwargs=policy_kwargs, spans_by_minute=spans_by_minute, moments=[moment, later])
        _assert_same_outcome(grouped.id, plain.id)
        assert store.calls.count("service_red") == 0, name
        assert store.calls.count("dependency_red") == 0, name


@pytest.mark.django_db
def test_endpoint_version_and_instance_product_matches_per_target():
    moment = _minute()
    later = moment + timedelta(minutes=1)
    grouped, plain, store = _run_pair(
        policy_kwargs={
            "endpoints": ["GET /pay", "GET /ok"],
            "endpoint_mode": ApmPolicy.EndpointMode.SELECTED,
            "version_mode": ApmPolicy.VersionMode.SPECIFIC,
            "versions": ["v1", "v2"],
            "instance_mode": ApmPolicy.InstanceMode.GROUPED,
        },
        spans_by_minute=[
            [
                _live(moment, trace_id="hit", span_id="hit", name="GET /pay", version="v1", instance_id="pod-a", status="error"),
                _live(moment, trace_id="ok", span_id="ok", name="GET /ok", version="v2", instance_id="pod-b"),
            ],
            [
                _live(later, trace_id="hit2", span_id="hit2", name="GET /pay", version="v1", instance_id="pod-a"),
                _live(later, trace_id="ok2", span_id="ok2", name="GET /ok", version="v2", instance_id="pod-b"),
            ],
        ],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("service_red") == 0
    # 汇总一次，另一次只为服务级 Top 操作补端点维度；两轮评估各一对。
    assert store.calls.count("service_red_grouped") == 4


@pytest.mark.django_db
def test_service_mode_keeps_one_target_query():
    moment = _minute()
    service = _next_service("service-mode")
    store = RecordingStore(
        _stamp(service, [_live(moment, trace_id="a", span_id="a", status="error"), _live(moment, trace_id="b", span_id="b", name="GET /b")])
    )
    policy = _policy(service)
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red_grouped") == 0
    assert store.calls.count("service_red") == 1
    assert ApmPolicyTargetState.objects.filter(policy=policy).count() == 1


@pytest.mark.django_db
def test_http_dependencies_stay_on_the_per_target_path_and_match():
    moment = _minute()
    later = moment + timedelta(minutes=1)

    def _http(moment, trace_id, name, route, *, status="ok"):
        return _live(
            moment,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name=name,
            status=status,
            attributes={"http.request.method": name, "http.route": route, "peer.service": "billing"},
        )

    spans_by_minute = [
        [_http(moment, "users", "GET", "/users", status="error"), _http(moment, "orders", "POST", "/orders", status="error")],
        [_http(later, "users2", "GET", "/users"), _http(later, "orders2", "POST", "/orders")],
    ]
    grouped, plain, store = _run_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "http", "system": "billing", "statement": "GET /users"},
                {"channel": "http", "system": "billing", "statement": "POST /orders"},
            ],
        },
        spans_by_minute=spans_by_minute,
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red_grouped") == 0
    assert store.calls.count("dependency_red") == 4


@pytest.mark.django_db
def test_mixed_http_and_database_groups_only_database_targets():
    moment = _minute()
    later = moment + timedelta(minutes=1)

    def _db(moment, trace_id, statement, *, status="ok"):
        return _live(
            moment,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="SELECT",
            status=status,
            attributes={"db.system.name": "mysql", "db.statement": statement},
        )

    def _http(moment, trace_id, *, status="ok"):
        return _live(
            moment,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="GET",
            status=status,
            attributes={"http.request.method": "GET", "http.route": "/users", "peer.service": "billing"},
        )

    grouped, plain, store = _run_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "http", "system": "billing", "statement": "GET /users"},
                {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                {"channel": "database", "system": "mysql", "statement": "SELECT users"},
            ],
        },
        spans_by_minute=[
            [
                _http(moment, "http1", status="error"),
                _db(moment, "orders", "SELECT orders", status="error"),
                _db(moment, "users", "SELECT users"),
            ],
            [
                _http(later, "http2"),
                _db(later, "orders2", "SELECT orders"),
                _db(later, "users2", "SELECT users"),
            ],
        ],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red_grouped") == 2
    assert store.calls.count("dependency_red") == 2


@pytest.mark.django_db
def test_overlapping_database_statement_falls_back_to_per_target():
    moment = _minute()
    later = moment + timedelta(minutes=1)

    def _db(moment, trace_id, *, status="ok"):
        return _live(
            moment,
            trace_id=trace_id,
            span_id=trace_id,
            kind="client",
            name="SELECT",
            status=status,
            attributes={"db.system.name": "mysql", "db.statement": "SELECT orders"},
        )

    grouped, plain, store = _run_pair(
        policy_kwargs={
            "target_kind": ApmPolicy.TargetKind.DEPENDENCY,
            "dependencies": [
                {"channel": "database", "system": "mysql", "statement": "SELECT orders"},
                {"channel": "database", "system": "mysql", "statement": "SELECT"},
            ],
        },
        spans_by_minute=[
            [_db(moment, "a", status="error"), _db(moment, "b", status="error")],
            [_db(later, "c"), _db(later, "d")],
        ],
        moments=[moment, later],
    )

    _assert_same_outcome(grouped.id, plain.id)
    assert store.calls.count("dependency_red_grouped") == 2
    assert store.calls.count("dependency_red") == 4
    assert ApmPolicyTargetState.objects.filter(policy=grouped, last_failed_at__isnull=False).count() == 0


@pytest.mark.django_db
def test_current_window_store_calls_do_not_grow_with_target_count():
    moment = _minute()
    counted = [_call_counts(3, moment), _call_counts(30, moment)]
    assert counted[0] == counted[1]
    assert counted[0]["service_red"] == 0
    assert counted[0]["service_red_grouped"] == 1
    assert counted[0]["service_endpoints"] == 1


@pytest.mark.django_db
def test_multi_condition_same_window_is_still_one_grouped_read():
    moment = _minute()
    service = _next_service("multi-condition")
    policy = _policy(
        service,
        endpoints=["GET /pay", "GET /ok"],
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        conditions=[
            {
                "ref": "a",
                "role": "regular",
                "metric_type": "error_rate",
                "compare_mode": "absolute",
                "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.5"}],
                "slow_threshold_ms": 200,
                "apdex_threshold_ms": 200,
            },
            {
                "ref": "b",
                "role": "regular",
                "metric_type": "p95",
                "compare_mode": "absolute",
                "thresholds": [{"severity": "warning", "comparator": "gt", "value": "10"}],
                "slow_threshold_ms": 200,
                "apdex_threshold_ms": 200,
            },
        ],
    )
    store = RecordingStore(
        _stamp(
            service,
            [
                _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error", duration_ms=400),
                _live(moment, trace_id="ok", span_id="ok", name="GET /ok", duration_ms=50),
            ],
        )
    )
    DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red_grouped") == 1
    assert store.calls.count("service_red") == 0


@pytest.mark.django_db
def test_unique_span_limit_falls_back_to_per_target_for_the_round(caplog):
    moment = _minute()
    spans = [
        _live(moment, trace_id="a", span_id="a", name="GET /a", status="error"),
        _live(moment, trace_id="b", span_id="b", name="GET /b"),
        _live(moment, trace_id="c", span_id="c", name="GET /c"),
    ]
    service = _next_service("limit")
    stamped = _stamp(service, spans)
    limited = RecordingStore(stamped, unique_span_limit=2)
    plain = RecordingStore(list(stamped), grouped=False)
    kwargs = {"endpoints": ["GET /a", "GET /b", "GET /c"], "endpoint_mode": ApmPolicy.EndpointMode.SELECTED}
    limited_policy = _policy(service, name="limited", **kwargs)
    plain_policy = _policy(service, name="plain-limit", **kwargs)
    caplog.set_level(logging.DEBUG, logger="apm")
    DjangoApmPolicyService(limited, InMemoryNotificationDispatcher()).evaluate(limited_policy.id, evaluated_at=moment)
    DjangoApmPolicyService(plain, InMemoryNotificationDispatcher()).evaluate(plain_policy.id, evaluated_at=moment)

    _assert_same_outcome(limited_policy.id, plain_policy.id, require_recovery=False)
    assert limited.calls.count("service_red_grouped") == 1
    assert limited.calls.count("service_red") == 3
    assert ApmPolicyTargetState.objects.filter(policy=limited_policy, last_failed_at__isnull=False).count() == 0
    warnings = [record for record in caplog.records if record.name == "apm" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == "event=apm_policy_grouped_read_fallback policy_id=%s failed_stage=%s error_type=%s"
    assert record.args == (str(limited_policy.id), "grouped_red", "TelemetryUniqueSpanLimitExceeded")
    assert record.getMessage() == (
        f"event=apm_policy_grouped_read_fallback policy_id={limited_policy.id} failed_stage=grouped_red error_type=TelemetryUniqueSpanLimitExceeded"
    )
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], RuntimeError)
    assert record.exc_info[1].args == ("TelemetryUniqueSpanLimitExceeded",)
    rendered = logging.Formatter().format(record)
    assert rendered.count("Traceback") == 1
    assert "GET /a" not in rendered
    assert "GET /a" not in record.getMessage()


@pytest.mark.django_db
def test_grouped_query_failure_marks_every_target_and_retries_the_round():
    moment = _minute()
    service = _next_service("grouped-failure")
    policy = _policy(
        service,
        endpoints=["GET /a", "GET /b", "GET /c"],
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
    )
    store = UnavailableGroupedStore(
        _stamp(
            service,
            [
                _live(moment, trace_id="a", span_id="a", name="GET /a", status="error"),
                _live(moment, trace_id="b", span_id="b", name="GET /b"),
                _live(moment, trace_id="c", span_id="c", name="GET /c"),
            ],
        )
    )

    with pytest.raises(TelemetryStoreUnavailable, match="grouped down"):
        DjangoApmPolicyService(store, InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=moment)

    states = list(ApmPolicyTargetState.objects.filter(policy=policy))
    assert len(states) == 3
    assert all(state.last_failed_at is not None for state in states)
    assert all(state.evaluation_cursor == "" for state in states)
    assert ApmAlert.objects.filter(policy=policy).count() == 0
    assert store.calls.count("service_red") == 0
    assert not isinstance(store.error, TelemetryGroupedReadFallback)


@pytest.mark.django_db
def test_test_query_and_dry_run_use_the_grouped_read():
    moment = _minute()
    spans = [
        _live(moment, trace_id="pay", span_id="pay", name="GET /pay", status="error", duration_ms=400),
        _live(moment, trace_id="ok", span_id="ok", name="GET /ok", duration_ms=50),
    ]
    service = _next_service("preview")
    policy = _policy(service, endpoints=["GET /pay", "GET /ok"], endpoint_mode=ApmPolicy.EndpointMode.SELECTED)
    stamped = _stamp(service, spans)
    grouped = RecordingStore(stamped)
    plain = RecordingStore(list(stamped), grouped=False)
    grouped_runner = DjangoApmPolicyService(grouped, InMemoryNotificationDispatcher())
    plain_runner = DjangoApmPolicyService(plain, InMemoryNotificationDispatcher())

    grouped_result = grouped_runner.test_query(policy, evaluated_at=moment, endpoint="GET /pay")
    plain_result = plain_runner.test_query(policy, evaluated_at=moment, endpoint="GET /pay")
    dry_run = grouped_runner.dry_run(policy, evaluated_at=moment)
    pay = next(item for item in dry_run["items"] if item["endpoint"] == "GET /pay")

    assert grouped.calls.count("service_red") == 0
    assert grouped.calls.count("service_red_grouped") == 2
    assert grouped_result.value == plain_result.value
    assert grouped_result.series == plain_result.series
    assert pay["compared_value"] == grouped_runner._decimal_text(grouped_result.value)


@pytest.mark.django_db
def test_version_targets_keep_the_same_top_endpoints_without_per_target_reads():
    moment = _minute()
    spans = [
        _live(moment, trace_id="a", span_id="a", version="v1", name="GET /a", duration_ms=100),
        _live(moment, trace_id="a2", span_id="a2", version="v1", name="GET /a", duration_ms=100),
        _live(moment, trace_id="b", span_id="b", version="v1", name="GET /b", duration_ms=100),
        _live(moment, trace_id="c", span_id="c", version="v2", name="GET /c", duration_ms=100),
    ]
    service = _next_service("tops")
    policy = _policy(service, version_mode=ApmPolicy.VersionMode.SPECIFIC, versions=["v1", "v2"])
    store = RecordingStore(_stamp(service, spans))
    runner = ReadingPolicyService(store, InMemoryNotificationDispatcher())
    runner.evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red") == 0
    window_start = moment - timedelta(minutes=1)
    for endpoint, version, instance_id, top_endpoints in runner.reads:
        direct = store.inner.service_red(
            ServiceMetricQuery(
                service_namespace=service.namespace,
                service_name=service.name,
                environment="production",
                started_at=window_start,
                ended_at=moment,
                include_breakdown=True,
                include_endpoints=True,
                endpoint=endpoint,
                version=version,
                instance_id=instance_id,
                slow_threshold_ms=200,
                apdex_threshold_ms=200,
            )
        )
        assert top_endpoints == direct.top_endpoints


@pytest.mark.django_db
def test_instance_top_endpoints_follow_the_exact_dedup_query():
    moment = _minute()
    spans = [
        _live(moment, trace_id="hot-a", span_id="hot-a", instance_id="pod-a", name="GET /hot", duration_ms=100),
        _live(moment, trace_id="hot-b", span_id="hot-b", instance_id="pod-b", name="GET /hot", duration_ms=100),
        _live(moment, trace_id="cold", span_id="cold", instance_id="pod-b", name="GET /cold", duration_ms=50),
    ]
    service = _next_service("instance-tops")
    policy = _policy(service, instance_mode=ApmPolicy.InstanceMode.GROUPED)
    store = RecordingStore(_stamp(service, spans))
    runner = ReadingPolicyService(store, InMemoryNotificationDispatcher())
    runner.evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped") == 2
    tops = {instance_id: endpoints for _endpoint, _version, instance_id, endpoints in runner.reads}
    assert tops["pod-a"] == tops["pod-b"]
    assert [item.endpoint for item in tops["pod-a"]] == ["GET /hot", "GET /cold"]
    assert tops["pod-a"][0].request_rate == 2 / 60
    direct = store.inner.service_red(
        ServiceMetricQuery(
            service_namespace=service.namespace,
            service_name=service.name,
            environment="production",
            started_at=moment - timedelta(minutes=1),
            ended_at=moment,
            include_breakdown=True,
            include_endpoints=True,
            instance_id="pod-a",
            slow_threshold_ms=200,
            apdex_threshold_ms=200,
        )
    )
    assert tops["pod-a"] == direct.top_endpoints


@pytest.mark.django_db
def test_endpoint_instance_top_endpoints_include_other_instances():
    moment = _minute()
    spans = [
        _live(moment, trace_id="a", span_id="a", instance_id="pod-a", name="GET /pay", duration_ms=100),
        _live(moment, trace_id="b", span_id="b", instance_id="pod-b", name="GET /pay", duration_ms=400),
    ]
    service = _next_service("endpoint-instance-tops")
    policy = _policy(
        service,
        endpoints=["GET /pay"],
        endpoint_mode=ApmPolicy.EndpointMode.SELECTED,
        instance_mode=ApmPolicy.InstanceMode.GROUPED,
    )
    store = RecordingStore(_stamp(service, spans))
    runner = ReadingPolicyService(store, InMemoryNotificationDispatcher())
    runner.evaluate(policy.id, evaluated_at=moment)

    assert store.calls.count("service_red") == 0
    assert store.calls.count("service_red_grouped") == 2
    pay_tops = [endpoints for endpoint, _version, _instance, endpoints in runner.reads if endpoint == "GET /pay"]
    assert len(pay_tops) == 2
    assert pay_tops[0] == pay_tops[1]
    assert pay_tops[0][0].endpoint == "GET /pay"
    assert pay_tops[0][0].request_rate == 2 / 60
    assert pay_tops[0][0].p95_ms == 400
