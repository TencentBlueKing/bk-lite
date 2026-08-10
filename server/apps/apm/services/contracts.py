from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping, Protocol, Sequence
from uuid import UUID

from apps.apm.models import ApmPolicy, ApmService, ApmServiceInstance


@dataclass(frozen=True)
class IngestSnippetRequest:
    language: str
    runtime: str
    endpoint: str
    service_namespace: str
    service_name: str
    service_version: str
    environment: str


@dataclass(frozen=True)
class IngestSnippet:
    environment: Mapping[str, str]
    code: str


@dataclass(frozen=True)
class CatalogDiscovery:
    service_namespace: str | None
    service_name: str
    instance_id: str | None
    environment: str
    version: str = ""
    seen_at: datetime | None = None


@dataclass(frozen=True)
class CatalogDiscoveryResult:
    service: ApmService | None
    instance: ApmServiceInstance | None
    missing_instance_identity: bool = False


@dataclass(frozen=True)
class CatalogReconcileResult:
    discovered_services: int
    discovered_instances: int
    missing_instance_identities: int
    archived_services: int
    archived_instances: int
    unknown_applications: int = 0
    invalid_activities: int = 0


@dataclass(frozen=True)
class TraceSearchQuery:
    started_at: datetime
    ended_at: datetime
    service_namespace: str | None = None
    service_name: str | None = None
    environment: str | None = None
    instance_id: str | None = None
    span_name: str | None = None
    status: str | None = None
    min_duration_ms: float | None = None
    max_duration_ms: float | None = None
    cursor: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    started_at: datetime
    duration_ms: float
    service_namespace: str
    service_name: str
    environment: str
    instance_id: str | None
    status: str
    root_span_name: str = ""
    span_count: int = 0


@dataclass(frozen=True)
class SpanSearchQuery:
    started_at: datetime
    ended_at: datetime
    service_name: str
    environment: str
    service_namespace: str | None = None
    instance_id: str | None = None
    span_name: str | None = None
    status: str | None = None
    kind: str | None = None
    min_duration_ms: float | None = None
    max_duration_ms: float | None = None
    cursor: str | None = None
    limit: int = 50


@dataclass(frozen=True)
class SpanSummary:
    trace_id: str
    span_id: str
    started_at: datetime
    duration_ms: float
    service_namespace: str
    service_name: str
    environment: str
    instance_id: str | None
    status: str
    name: str
    kind: str
    http_method: str | None = None
    http_status_code: str | None = None


@dataclass(frozen=True)
class SpanPage:
    items: tuple[SpanSummary, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class SpanDetail:
    span_id: str
    parent_span_id: str | None
    name: str
    started_at: datetime
    duration_ms: float
    status: str
    attributes: Mapping[str, object] = field(default_factory=dict)
    service_namespace: str = ""
    service_name: str = ""
    environment: str = ""
    instance_id: str | None = None
    kind: str = "unspecified"


@dataclass(frozen=True)
class TraceDetail:
    trace_id: str
    spans: tuple[SpanDetail, ...]
    service_namespace: str
    service_name: str
    environment: str
    instance_id: str | None
    truncated: bool = False


@dataclass(frozen=True)
class TracePage:
    items: tuple[TraceSummary, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class TopologyTarget:
    service_namespace: str
    service_name: str
    environment: str


@dataclass(frozen=True)
class TopologyDependencyQuery:
    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class ServiceDependency:
    parent_service_name: str
    child_service_name: str
    call_count: int


@dataclass(frozen=True)
class TopologyNode:
    id: str
    service_namespace: str
    service_name: str
    environment: str
    health: str
    sampled_spans: int
    error_spans: int


@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    health: str
    sampled_calls: int
    error_calls: int
    average_duration_ms: float


@dataclass(frozen=True)
class TopologyGraph:
    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]
    sampled_traces: int
    truncated: bool
    data_state: str
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceMetricQuery:
    service_namespace: str
    service_name: str
    environment: str
    started_at: datetime
    ended_at: datetime
    include_breakdown: bool = False


@dataclass(frozen=True)
class ServiceRedPoint:
    timestamp: datetime
    request_rate: float | None
    error_rate: float | None
    p95_ms: float | None
    p99_ms: float | None


@dataclass(frozen=True)
class ServiceEndpointRed:
    endpoint: str
    request_rate: float
    error_rate: float | None
    p95_ms: float | None
    p99_ms: float | None


@dataclass(frozen=True)
class ServiceRed:
    request_rate: float | None
    error_rate: float | None
    p95_ms: float | None
    p99_ms: float | None
    timeseries: tuple[ServiceRedPoint, ...] = ()
    top_endpoints: tuple[ServiceEndpointRed, ...] = ()


@dataclass(frozen=True)
class SloMetricQuery:
    service_namespace: str
    service_name: str
    environment: str
    started_at: datetime
    ended_at: datetime
    sli_type: str
    endpoint: str = ""
    latency_threshold_ms: int | None = None


@dataclass(frozen=True)
class SloMeasurement:
    compliance_percent: float | None
    good_rate: float | None
    total_rate: float | None
    data_state: MetricDataState


@dataclass(frozen=True)
class SloEvaluation:
    current_rate: float | None
    budget_remaining: float | None
    data_state: str
    started_at: datetime | None
    ended_at: datetime
    reason: str = ""


@dataclass(frozen=True)
class InstanceActivityQuery:
    started_at: datetime
    ended_at: datetime


@dataclass(frozen=True)
class InstanceActivity:
    service_namespace: str
    service_name: str
    instance_id: str | None
    environment: str
    version: str
    last_seen_at: datetime


@dataclass(frozen=True)
class PublishResult:
    accepted: int
    duplicates: int = 0
    failed: int = 0


class MetricDataState(StrEnum):
    AVAILABLE = "available"
    NO_DATA = "no_data"


@dataclass(frozen=True)
class PolicyQueryResult:
    value: Decimal | None
    breached: bool | None
    evaluated_at: datetime
    data_state: MetricDataState = MetricDataState.AVAILABLE


@dataclass(frozen=True)
class NotificationChannel:
    id: int
    name: str
    channel_type: str
    description: str
    delivery_mode: str
    recipient_mode: str
    availability: str


@dataclass(frozen=True)
class NotificationRecipient:
    id: int
    username: str
    display_name: str


@dataclass(frozen=True)
class NotificationDelivery:
    delivery_key: str
    channel_id: int
    organization_ids: tuple[int, ...]
    recipients: tuple[str, ...]
    title: str
    body: str
    event_payload: Mapping[str, object]


@dataclass(frozen=True)
class NotificationDeliveryResult:
    delivered: bool
    code: str
    retryable: bool
    message: str


class TraceStore(Protocol):
    def search(self, query: TraceSearchQuery) -> TracePage: ...

    def search_spans(self, query: SpanSearchQuery) -> SpanPage: ...

    def get_trace(self, trace_id: str) -> TraceDetail | None: ...


class MetricStore(Protocol):
    def service_red(self, query: ServiceMetricQuery) -> ServiceRed: ...

    def slo_measurement(self, query: SloMetricQuery) -> SloMeasurement: ...

    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]: ...


class TopologyStore(Protocol):
    def service_dependencies(
        self,
        query: TopologyDependencyQuery,
    ) -> tuple[ServiceDependency, ...]: ...


class TelemetryStore(TraceStore, MetricStore, TopologyStore, Protocol):
    """APM 对单一 VictoriaTraces 数据面的完整查询边界。"""


class NotificationDispatcher(Protocol):
    def dispatch(self, delivery: NotificationDelivery) -> NotificationDeliveryResult: ...


class IntegrationConfigurationService(Protocol):
    def render_snippet(self, request: IngestSnippetRequest) -> IngestSnippet: ...


class TelemetryCatalogService(Protocol):
    def discover(self, discovery: CatalogDiscovery) -> CatalogDiscoveryResult: ...

    def set_service_organizations(
        self,
        service_id: UUID,
        organization_ids: Sequence[int],
        *,
        actor: str,
    ) -> ApmService: ...

    def set_instance_organizations(
        self,
        instance_id: UUID,
        organization_ids: Sequence[int],
        *,
        actor: str,
    ) -> ApmServiceInstance: ...

    def archive_service(self, service_id: UUID, *, reason: str, actor: str) -> ApmService: ...

    def archive_instance(self, instance_id: UUID, *, reason: str, actor: str) -> ApmServiceInstance: ...

    def restore_service(self, service_id: UUID, *, actor: str) -> ApmService: ...

    def restore_instance(self, instance_id: UUID, *, actor: str) -> ApmServiceInstance: ...

    def archive_stale(self, *, observed_at: datetime) -> tuple[int, int]: ...


class TelemetryQueryService(Protocol):
    def service_red(self, query: ServiceMetricQuery) -> ServiceRed: ...

    def search_traces(self, query: TraceSearchQuery) -> TracePage: ...

    def get_trace(self, trace_id: str) -> TraceDetail | None: ...


class ApmPolicyService(Protocol):
    def save_policy(self, policy: ApmPolicy) -> ApmPolicy: ...

    def evaluate(self, policy_id: UUID, *, evaluated_at: datetime) -> None: ...

    def test_query(self, policy: ApmPolicy, *, evaluated_at: datetime) -> PolicyQueryResult: ...

    def retry_pending_events(self, *, limit: int = 100) -> PublishResult: ...
