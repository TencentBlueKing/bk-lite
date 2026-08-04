from __future__ import annotations

from collections.abc import Iterable, Sequence

from apps.apm.services.contracts import (
    InstanceActivity,
    InstanceActivityQuery,
    NotificationDelivery,
    NotificationDeliveryResult,
    ServiceMetricQuery,
    ServiceRed,
    SloMeasurement,
    SloMetricQuery,
    TraceDetail,
    TracePage,
    TraceSearchQuery,
    TraceSummary,
)
from apps.apm.services.identity import normalize_identity


class InMemoryTraceStore:
    def __init__(
        self,
        *,
        summaries: Iterable[TraceSummary] = (),
        details: Iterable[TraceDetail] = (),
    ):
        self._summaries = {item.trace_id: item for item in summaries}
        self._details = {item.trace_id: item for item in details}

    def add(self, summary: TraceSummary, detail: TraceDetail) -> None:
        if summary.trace_id != detail.trace_id:
            raise ValueError("Trace 摘要与详情的 trace_id 不一致")
        self._summaries[summary.trace_id] = summary
        self._details[detail.trace_id] = detail

    def search(self, query: TraceSearchQuery) -> TracePage:
        if query.limit < 1:
            raise ValueError("limit 必须大于 0")
        start_index = int(query.cursor or "0")
        items = [
            item
            for item in self._summaries.values()
            if query.started_at <= item.started_at <= query.ended_at
            and (
                query.service_namespace is None
                or normalize_identity(item.service_namespace) == normalize_identity(query.service_namespace)
            )
            and (
                query.service_name is None
                or normalize_identity(item.service_name) == normalize_identity(query.service_name)
            )
            and (query.environment is None or item.environment == query.environment)
            and (query.instance_id is None or item.instance_id == query.instance_id)
        ]
        items.sort(key=lambda item: (item.started_at, item.trace_id), reverse=True)
        page_items = tuple(items[start_index : start_index + query.limit])
        next_index = start_index + len(page_items)
        next_cursor = str(next_index) if next_index < len(items) else None
        return TracePage(items=page_items, next_cursor=next_cursor)

    def get_trace(self, trace_id: str) -> TraceDetail | None:
        return self._details.get(trace_id)


class InMemoryMetricStore:
    def __init__(
        self,
        *,
        service_metrics: Iterable[tuple[ServiceMetricQuery, ServiceRed]] = (),
        slo_measurements: Iterable[tuple[SloMetricQuery, SloMeasurement]] = (),
        activities: Iterable[InstanceActivity] = (),
    ):
        self._service_metrics = list(service_metrics)
        self._slo_measurements = list(slo_measurements)
        self._activities = list(activities)

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
        return [
            item
            for item in self._activities
            if query.started_at <= item.last_seen_at <= query.ended_at
        ]


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
