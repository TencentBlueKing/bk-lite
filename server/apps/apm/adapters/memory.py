from __future__ import annotations

from collections.abc import Iterable

from apps.apm.services.contracts import (
    DeploymentReleaseQuery,
    ENTRY_SPAN_KINDS,
    InferredDeploymentRelease,
    InstanceActivity,
    InstanceActivityQuery,
    MetricDataState,
    NotificationDelivery,
    NotificationDeliveryResult,
    ServiceDependency,
    ServiceErrorBreakdown,
    ServiceErrorBreakdownQuery,
    ServiceErrorSampleTrace,
    ServiceMetricQuery,
    ServiceRed,
    SloMeasurement,
    SloMetricQuery,
    SpanPage,
    SpanSearchQuery,
    SpanSummary,
    TopologyDependencyQuery,
    TopologySampleQuery,
    TopologyTraceSample,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceSummary,
)
from apps.apm.services.error_breakdown import (
    RawErrorGroup,
    attach_samples,
    coalesce_error_type,
    merge_error_groups,
    rank_failed_endpoints,
)
from apps.apm.services.identity import normalize_identity


class InMemoryTraceStore:
    def __init__(
        self,
        *,
        summaries: Iterable[TraceSummary] = (),
        details: Iterable[TraceDetail] = (),
        spans: Iterable[SpanSummary] = (),
        dependencies: Iterable[ServiceDependency] = (),
    ):
        self._summaries = {item.trace_id: item for item in summaries}
        self._details = {item.trace_id: item for item in details}
        self._spans = list(spans)
        self._dependencies = tuple(dependencies)

    def add(self, summary: TraceSummary, detail: TraceDetail) -> None:
        if summary.trace_id != detail.trace_id:
            raise ValueError("Trace 摘要与详情的 trace_id 不一致")
        self._summaries[summary.trace_id] = summary
        self._details[detail.trace_id] = detail

    def add_span(self, span: SpanSummary) -> None:
        self._spans.append(span)

    def search(self, query: TraceSearchQuery) -> TracePage:
        if query.limit < 1:
            raise ValueError("limit 必须大于 0")
        start_index = int(query.cursor or "0")
        items = [
            item
            for item in self._summaries.values()
            if query.started_at <= item.started_at <= query.ended_at
            and (query.service_namespace is None or normalize_identity(item.service_namespace) == normalize_identity(query.service_namespace))
            and (query.service_name is None or normalize_identity(item.service_name) == normalize_identity(query.service_name))
            and (query.environment is None or item.environment == query.environment)
            and (query.instance_id is None or item.instance_id == query.instance_id)
            and (query.span_name is None or item.root_span_name == query.span_name)
            and (query.status is None or item.status == query.status)
            and (query.min_duration_ms is None or item.duration_ms >= query.min_duration_ms)
            and (query.max_duration_ms is None or item.duration_ms <= query.max_duration_ms)
        ]
        items.sort(key=lambda item: (item.started_at, item.trace_id), reverse=True)
        page_items = tuple(items[start_index : start_index + query.limit])
        next_index = start_index + len(page_items)
        next_cursor = str(next_index) if next_index < len(items) else None
        return TracePage(items=page_items, next_cursor=next_cursor)

    def search_spans(self, query: SpanSearchQuery) -> SpanPage:
        if query.limit < 1:
            raise ValueError("limit 必须大于 0")
        start_index = int(query.cursor or "0")
        items = [
            item
            for item in self._spans
            if query.started_at <= item.started_at <= query.ended_at
            and (query.service_name is None or normalize_identity(item.service_name) == normalize_identity(query.service_name))
            and (query.environment is None or item.environment == query.environment)
            and (query.service_namespace is None or normalize_identity(item.service_namespace) == normalize_identity(query.service_namespace))
            and (query.instance_id is None or item.instance_id == query.instance_id)
            and (query.span_name is None or item.name == query.span_name)
            and (query.status is None or item.status == query.status)
            and (query.kind is None or item.kind == query.kind)
            and (query.kinds is None or item.kind in query.kinds)
            and (query.min_duration_ms is None or item.duration_ms >= query.min_duration_ms)
            and (query.max_duration_ms is None or item.duration_ms <= query.max_duration_ms)
        ]
        items.sort(key=lambda item: (item.started_at, item.span_id), reverse=True)
        page_items = tuple(items[start_index : start_index + query.limit])
        next_index = start_index + len(page_items)
        next_cursor = str(next_index) if next_index < len(items) else None
        return SpanPage(items=page_items, next_cursor=next_cursor)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        return self._details.get(trace_id)

    def service_error_breakdown(self, query: ServiceErrorBreakdownQuery) -> ServiceErrorBreakdown:
        if query.sample_limit < 1 or query.sample_limit > 50:
            raise ValueError("sample_limit 必须在 1 到 50 之间")
        spans = [
            item
            for item in self._spans
            if query.started_at <= item.started_at <= query.ended_at
            and normalize_identity(item.service_namespace) == normalize_identity(query.service_namespace)
            and normalize_identity(item.service_name) == normalize_identity(query.service_name)
            and item.environment == query.environment
        ]
        entry = [item for item in spans if item.kind in ENTRY_SPAN_KINDS]
        if not entry:
            return ServiceErrorBreakdown(None, None, None, MetricDataState.NO_DATA)
        entry_errors = [item for item in entry if item.status == "error"]
        request_count = len(entry)
        error_count = len(entry_errors)
        endpoint_counts: dict[str, list[int]] = {}
        for item in entry:
            bucket = endpoint_counts.setdefault(item.name, [0, 0])
            bucket[0] += 1
            if item.status == "error":
                bucket[1] += 1
        failed_endpoints, other_error_count = rank_failed_endpoints(
            [(endpoint, counts[0], counts[1]) for endpoint, counts in endpoint_counts.items()],
            total_errors=error_count,
        )
        if error_count == 0:
            return ServiceErrorBreakdown(
                request_count,
                0,
                0.0,
                MetricDataState.AVAILABLE,
                failed_endpoints,
                other_error_count,
            )
        error_spans = [item for item in spans if item.status == "error"]
        types = merge_error_groups(
            [
                RawErrorGroup(
                    kind=item.kind,
                    exception_type=item.exception_type or "",
                    span_error_type=item.span_error_type or "",
                    status_message=item.status_message or "",
                    http_status=item.http_status_code or "",
                    exception_message=item.exception_message or "",
                    count=1,
                    last_seen_at=item.started_at,
                )
                for item in error_spans
            ]
        )
        error_types = []
        for item in types:
            matching = [
                span
                for span in error_spans
                if coalesce_error_type(
                    exception_type=span.exception_type or "",
                    span_error_type=span.span_error_type or "",
                    status_message=span.status_message or "",
                    http_status=span.http_status_code or "",
                )
                == item.error_type
            ]
            matching.sort(key=lambda span: (span.started_at, span.span_id), reverse=True)
            error_types.append(
                attach_samples(
                    item,
                    [
                        ServiceErrorSampleTrace(
                            trace_id=span.trace_id,
                            span_id=span.span_id,
                            endpoint=span.name,
                            started_at=span.started_at,
                        )
                        for span in matching
                    ],
                )
            )
        recent = tuple(
            sorted(entry_errors, key=lambda item: (item.started_at, item.span_id), reverse=True)[: query.sample_limit]
        )
        return ServiceErrorBreakdown(
            request_count=request_count,
            error_count=error_count,
            error_rate=error_count / request_count,
            data_state=MetricDataState.AVAILABLE,
            failed_endpoints=failed_endpoints,
            other_error_count=other_error_count,
            error_types=tuple(error_types),
            recent_failures=recent,
        )

    def sample_traces(self, query: TopologySampleQuery) -> TopologyTraceSample:
        names = {normalize_identity(name) for name in query.service_names}
        items: list[TraceDetail] = []
        for detail in self._details.values():
            if not detail.spans:
                continue
            started_at = min(span.started_at for span in detail.spans)
            if not query.started_at <= started_at <= query.ended_at:
                continue
            if names and not any(normalize_identity(span.service_name) in names for span in detail.spans):
                continue
            if query.environment is not None and not any(span.environment == query.environment for span in detail.spans):
                continue
            items.append(detail)
        items.sort(key=lambda item: (min(span.started_at for span in item.spans), item.trace_id), reverse=True)
        truncated = len(items) > query.limit
        return TopologyTraceSample(traces=tuple(items[: query.limit]), truncated=truncated)

    def service_dependencies(self, query: TopologyDependencyQuery) -> tuple[ServiceDependency, ...]:
        return self._dependencies


class InMemoryMetricStore:
    def __init__(
        self,
        *,
        service_metrics: Iterable[tuple[ServiceMetricQuery, ServiceRed]] = (),
        slo_measurements: Iterable[tuple[SloMetricQuery, SloMeasurement]] = (),
        activities: Iterable[InstanceActivity] = (),
        deployment_releases: Iterable[InferredDeploymentRelease] = (),
    ):
        self._service_metrics = list(service_metrics)
        self._slo_measurements = list(slo_measurements)
        self._activities = list(activities)
        self._deployment_releases = list(deployment_releases)

    def set_service_red(self, query: ServiceMetricQuery, value: ServiceRed) -> None:
        self._service_metrics = [(key, item) for key, item in self._service_metrics if key != query]
        self._service_metrics.append((query, value))

    def add_activity(self, activity: InstanceActivity) -> None:
        self._activities.append(activity)

    def set_slo_measurement(self, query: SloMetricQuery, value: SloMeasurement) -> None:
        self._slo_measurements = [(key, item) for key, item in self._slo_measurements if key != query]
        self._slo_measurements.append((query, value))

    def service_red(self, query: ServiceMetricQuery) -> ServiceRed:
        return next(value for key, value in self._service_metrics if key == query)

    def slo_measurement(self, query: SloMetricQuery) -> SloMeasurement:
        return next(value for key, value in self._slo_measurements if key == query)

    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]:
        return [item for item in self._activities if query.started_at <= item.last_seen_at <= query.ended_at]

    def deployment_releases(self, query: DeploymentReleaseQuery) -> list[InferredDeploymentRelease]:
        return [item for item in self._deployment_releases if query.started_at <= item.first_seen_at <= query.ended_at]


class InMemoryNotificationDispatcher:
    def __init__(self, results: dict[int, NotificationDeliveryResult] | None = None):
        self.results = results or {}
        self.deliveries: list[NotificationDelivery] = []

    def dispatch(self, delivery: NotificationDelivery) -> NotificationDeliveryResult:
        self.deliveries.append(delivery)
        return self.results.get(
            delivery.channel_id,
            NotificationDeliveryResult(
                delivered=True,
                code="delivered",
                retryable=False,
                message="success",
            ),
        )
